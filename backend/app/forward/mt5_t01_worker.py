"""Explicitly started, read-only diagnostic workers. No execution authority.

Persisted status never resumes a worker automatically. Lease generations fence
late results at the same SQLite transaction as the decision commit.
"""
from datetime import datetime, timezone
import json
from threading import Event, RLock, Thread
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.brokers.base import BrokerHistoryError
from .bars import stamp
from .deployments import digest
from .mt5_t01_poll import poll_once
from .mt5_t01_runtime import T01DecisionRuntime

ACTIVE = ('STARTING', 'POLLING', 'WAITING', 'WAITING_SESSION', 'STOPPING')
STALE_SECONDS = 60


class WorkerFenced(ValueError):
    pass


class T01DiagnosticWorker:
    def __init__(self, database, connections, *, runtime=None, clock=lambda:datetime.now(timezone.utc), poll=poll_once):
        self.database, self.connections, self.clock, self.poll = database, connections, clock, poll
        self.runtime = runtime or T01DecisionRuntime(database)
        self.owner = str(uuid4())
        self.lock, self.tasks = RLock(), {}
        self.closed = False
        self._interval = 15
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_t01_workers(
                stream_id TEXT PRIMARY KEY REFERENCES mt5_t01_diagnostics(id),
                profile_id TEXT NOT NULL, account_key TEXT NOT NULL,
                owner TEXT NOT NULL, generation INTEGER NOT NULL,
                state TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
                last_cycle_at TEXT, last_decision_at TEXT, error_category TEXT,
                stop_requested INTEGER NOT NULL DEFAULT 0)''')
            c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS mt5_t01_active_account
                ON mt5_t01_workers(account_key)
                WHERE state IN ('STARTING','POLLING','WAITING','WAITING_SESSION','STOPPING')''')

    def _now(self):
        return stamp(self.clock())

    def _guard(self, c, identifier, generation):
        row = c.execute('SELECT owner,generation,stop_requested,state FROM mt5_t01_workers WHERE stream_id=?', (identifier,)).fetchone()
        if (self.closed or row is None or row[0] != self.owner or row[1] != generation
                or row[2] or row[3] not in ('STARTING','POLLING','WAITING','WAITING_SESSION')):
            raise WorkerFenced('T01 diagnostic worker stopped or superseded')

    def _cancelled(self, identifier, generation, event):
        if event.is_set():
            return True
        with self.database.connect() as c:
            try:
                self._guard(c, identifier, generation)
                return False
            except WorkerFenced:
                return True

    def start(self, identifier, profile_id):
        self.runtime._manual_only()
        with self.lock, self.runtime.registry.executing():
            if self.closed:
                raise ValueError('Diagnostic service is closed')
            task = self.tasks.get(identifier)
            if task and task['thread'].is_alive():
                if task['profile_id'] != profile_id:
                    raise ValueError('Diagnostic worker is bound to a different profile')
                return self.report(identifier)
            profile = self.connections._profile(profile_id)
            if profile.provider != 'mt5' or profile.environment != 'demo' or not profile.configured:
                raise ValueError('Enabled MT5 demo profile required')
            now = self._now()
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                row = c.execute('SELECT definition,definition_sha256 FROM mt5_t01_diagnostics WHERE id=?', (identifier,)).fetchone()
                if row is None or digest(json.loads(row[0])) != row[1]:
                    raise ValueError('Unknown or invalid diagnostic definition')
                definition = json.loads(row[0]); self.runtime._verify(definition)
                if self.connections._setting(self.connections._selection(profile)) != definition['account_key']:
                    raise ValueError('Selected MT5 account differs from diagnostic definition')
                old = c.execute('SELECT * FROM mt5_t01_workers WHERE stream_id=?', (identifier,)).fetchone()
                if old and old['state'] in ACTIVE:
                    age = (now-stamp(old['heartbeat_at'])).total_seconds()
                    if not age > STALE_SECONDS:
                        raise ValueError('Diagnostic worker ownership is still active; stop it before restarting')
                other = c.execute("SELECT stream_id FROM mt5_t01_workers WHERE account_key=? AND stream_id<>? AND state IN ('STARTING','POLLING','WAITING','WAITING_SESSION','STOPPING')", (definition['account_key'],identifier)).fetchone()
                if other:
                    raise ValueError('Another diagnostic stream holds this account; resolve it first')
                generation = old['generation']+1 if old else 1
                c.execute('''INSERT INTO mt5_t01_workers
                    (stream_id,profile_id,account_key,owner,generation,state,heartbeat_at,stop_requested)
                    VALUES(?,?,?,?,?,'STARTING',?,0) ON CONFLICT(stream_id) DO UPDATE SET
                    profile_id=excluded.profile_id,owner=excluded.owner,generation=excluded.generation,
                    state='STARTING',heartbeat_at=excluded.heartbeat_at,error_category=NULL,stop_requested=0''',
                    (identifier,profile_id,definition['account_key'],self.owner,generation,now.isoformat()))
            event = Event()
            thread = Thread(target=self._loop, args=(identifier,profile_id,generation,event),
                            name='t01-diagnostic-'+identifier[:8], daemon=True)
            self.tasks[identifier] = dict(thread=thread,event=event,generation=generation,profile_id=profile_id)
            try:
                thread.start()
            except Exception:
                self._finish(identifier,generation,'FAILED','worker_start_failed')
                self.tasks.pop(identifier, None)
                raise ValueError('Diagnostic worker could not start') from None
        return self.report(identifier)

    def _finish(self, identifier, generation, state, error=None):
        with self.database.connect() as c:
            c.execute('''UPDATE mt5_t01_workers SET state=?,error_category=?,heartbeat_at=?
                WHERE stream_id=? AND owner=? AND generation=?''',
                (state,error,self._now().isoformat(),identifier,self.owner,generation))

    def _loop(self, identifier, profile_id, generation, event):
        try:
            while not self._cancelled(identifier,generation,event):
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE'); self._guard(c,identifier,generation)
                    revision = c.execute('SELECT revision FROM mt5_t01_diagnostics WHERE id=?', (identifier,)).fetchone()[0]
                    local = self._now().astimezone(ZoneInfo('America/New_York'))
                    waiting = revision==0 and (local.hour,local.minute)!=(20,1)
                    if waiting:
                        c.execute("UPDATE mt5_t01_workers SET state='WAITING_SESSION',heartbeat_at=? WHERE stream_id=?", (self._now().isoformat(),identifier))
                if waiting:
                    if event.wait(self._interval): break
                    continue
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE'); self._guard(c,identifier,generation)
                    c.execute("UPDATE mt5_t01_workers SET state='POLLING',heartbeat_at=? WHERE stream_id=?", (self._now().isoformat(),identifier))
                try:
                    result = self.poll(self.runtime,self.connections,identifier,profile_id,
                        clock=self.clock, cancelled=lambda:self._cancelled(identifier,generation,event),
                        commit_guard=lambda c:self._guard(c,identifier,generation))
                    if result['status'] == 'cancelled':
                        break
                    if result['status'] not in ('decision_recorded','waiting_for_completed_minute'):
                        raise ValueError('Unexpected diagnostic cycle result')
                    decision_at = (result['decision']['decision_at'] if result['status']=='decision_recorded'
                                   else result.get('decision_at'))
                    with self.database.connect() as c:
                        c.execute('BEGIN IMMEDIATE'); self._guard(c,identifier,generation)
                        c.execute('''UPDATE mt5_t01_workers SET state='WAITING',heartbeat_at=?,last_cycle_at=?,
                            last_decision_at=COALESCE(?,last_decision_at),error_category=NULL WHERE stream_id=?''',
                            (self._now().isoformat(),self._now().isoformat(),decision_at,identifier))
                except BrokerHistoryError as exc:
                    if self._cancelled(identifier,generation,event):
                        break
                    if exc.category != 'busy':
                        self._finish(identifier,generation,'FAILED','broker_observation_failed'); return
                    with self.database.connect() as c:
                        c.execute('BEGIN IMMEDIATE'); self._guard(c,identifier,generation)
                        c.execute("UPDATE mt5_t01_workers SET state='WAITING',error_category='profile_busy',heartbeat_at=? WHERE stream_id=?", (self._now().isoformat(),identifier))
                if event.wait(self._interval):
                    break
        except WorkerFenced:
            pass
        except Exception:
            # Never persist provider/native exception text or credentials.
            try:
                self._finish(identifier,generation,'FAILED','diagnostic_cycle_failed')
            except Exception:
                pass  # Stale liveness remains visible if storage itself failed.
            return
        self._finish(identifier,generation,'STOPPED')

    def stop(self, identifier, *, join_timeout=2):
        self.runtime._manual_only()
        with self.lock:
            task = self.tasks.get(identifier)
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                row = c.execute('SELECT owner,generation,state FROM mt5_t01_workers WHERE stream_id=?', (identifier,)).fetchone()
                if row is None:
                    raise ValueError('Unknown diagnostic worker')
                if row['owner'] != self.owner:
                    raise ValueError('Diagnostic worker belongs to another process; inspect recovery state')
                if row['state'] in ACTIVE:
                    c.execute("UPDATE mt5_t01_workers SET stop_requested=1,state='STOPPING' WHERE stream_id=?", (identifier,))
            if task:
                task['event'].set()
        if task:
            task['thread'].join(timeout=join_timeout)
        return self.report(identifier)

    def close(self):
        with self.lock:
            self.closed = True
            identifiers = list(self.tasks)
            for task in self.tasks.values():
                task['event'].set()
        for identifier in identifiers:
            try:
                self.stop(identifier,join_timeout=0)
            except ValueError:
                pass  # A replacement process owns the newer generation.
        deadline = time.monotonic()+2
        for task in self.tasks.values():
            task['thread'].join(timeout=max(0,deadline-time.monotonic()))

    def report(self, identifier=None):
        with self.database.connect() as c:
            rows = c.execute('SELECT * FROM mt5_t01_workers'+(' WHERE stream_id=?' if identifier else '')+' ORDER BY rowid DESC LIMIT 500',
                             (identifier,) if identifier else ()).fetchall()
        now = self._now(); items = []
        with self.lock:
            for row in rows:
                task = self.tasks.get(row['stream_id'])
                alive = bool(row['owner']==self.owner and task and task['generation']==row['generation'] and task['thread'].is_alive())
                state = row['state']
                age = (now-stamp(row['heartbeat_at'])).total_seconds()
                if state in ACTIVE:
                    state = 'RECOVERY_REQUIRED' if not alive else 'STALLED' if not 0<=age<=STALE_SECONDS else state
                items.append(dict(id=row['stream_id'],stream_id=row['stream_id'],profile_id=row['profile_id'],state=state,
                    persisted_state=row['state'],thread_alive=alive,heartbeat_at=row['heartbeat_at'],
                    last_cycle_at=row['last_cycle_at'],last_decision_at=row['last_decision_at'],
                    error_category=row['error_category'],execution_enabled=False,mode='DIAGNOSTIC_ONLY'))
        return dict(items=items,execution_enabled=False)
