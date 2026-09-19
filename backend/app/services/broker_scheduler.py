"""Backend-owned read-only scheduling; persisted preferences and cooldowns."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, RLock, Thread
import json
import time

from app.brokers.base import BrokerHistoryError
from app.services.broker_connections import CAPABILITIES


class BrokerScheduler:
    def __init__(self, connections, database, *, clock=time.time):
        self.connections, self.database, self.clock = connections, database, clock
        self.lock, self.stop_event = RLock(), Event()
        self.active = set()
        self.pending = set()
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='broker-sync')
        self.thread = None

    def _load(self, profile_id):
        p = self.connections._profile(profile_id)
        minimum = 300 if p.provider == 'trading212' else 60
        saved = json.loads(self.database.get_setting('broker_auto_sync:' + profile_id) or '{}')
        return {'enabled': True, 'interval_seconds': minimum, 'next_at': self.clock()+minimum,
                'retry_until': 0, 'failures': 0, 'status': 'scheduled', **saved, 'minimum_seconds': minimum}

    def _save(self, profile_id, state):
        self.database.set_setting('broker_auto_sync:' + profile_id, json.dumps(state))

    def status(self, profile_id):
        with self.lock:
            state = self._load(profile_id)
            p = self.connections._profile(profile_id)
            enabled = state['enabled'] and p.configured and CAPABILITIES[p.provider]['supported']
            return {**state, 'eligible': bool(enabled),
                    'status': 'syncing' if profile_id in self.active else state['status'] if enabled else 'disabled',
                    'next_sync_at': datetime.fromtimestamp(max(state['next_at'],state['retry_until']),timezone.utc).isoformat() if enabled else None}

    def configure(self, profile_id, enabled, interval_seconds):
        with self.lock:
            state = self._load(profile_id)
            if interval_seconds < state['minimum_seconds'] or interval_seconds > 86400:
                raise BrokerHistoryError(f'Interval must be between {state["minimum_seconds"]} and 86400 seconds')
            state.update(enabled=enabled, interval_seconds=interval_seconds,
                         next_at=max(self.clock()+interval_seconds,state['retry_until']))
            self._save(profile_id, state)
            return self.status(profile_id)

    def sync_now(self, profile_id):
        with self.lock:
            state = self._load(profile_id)
            if profile_id in self.active:
                raise BrokerHistoryError('Sync is already running for this profile')
            if self.clock() < state['retry_until']:
                raise BrokerHistoryError('Provider cooldown is active; last good data is retained',status_code=429,retry_after=state['retry_until']-self.clock())
            self.active.add(profile_id)
        try:
            result = self.connections.sync(profile_id)
            with self.lock:
                state = self._load(profile_id)
                state.update(status='success', failures=0, retry_until=0, last_sync_at=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat(), next_at=self.clock()+state['interval_seconds'])
                self._save(profile_id,state)
            return result
        except Exception as exc:
            with self.lock:
                state = self._load(profile_id)
                failures = state['failures'] + 1
                delay = max(min(3600,state['interval_seconds']*2**min(failures,6)),getattr(exc,'retry_after',0) or 0)
                state.update(status='backoff',failures=failures,retry_until=self.clock()+delay,next_at=self.clock()+delay)
                self._save(profile_id,state)
            if isinstance(exc,BrokerHistoryError): raise
            raise BrokerHistoryError('Sync failed; last good broker state retained') from None
        finally:
            with self.lock:self.active.discard(profile_id)

    def tick(self):
        with self.lock:
            for profile_id in self.connections.profiles:
                state = self._load(profile_id)
                if self.database.get_setting('broker_auto_sync:'+profile_id) is None:
                    self._save(profile_id,state)
                p = self.connections._profile(profile_id)
                if not state['enabled'] or not p.configured or not CAPABILITIES[p.provider]['supported'] or profile_id in self.active or profile_id in self.pending:
                    continue
                if self.clock() < max(state['next_at'],state['retry_until']): continue
                # Reserve the due time before dispatch so subsequent ticks cannot
                # enqueue duplicate work while another provider uses a worker.
                state['next_at'] = self.clock()+state['interval_seconds']
                self._save(profile_id,state)
                self.pending.add(profile_id)
                self.pool.submit(self._scheduled,profile_id)

    def _scheduled(self, profile_id):
        try:
            if not self.stop_event.is_set(): self.sync_now(profile_id)
        except BrokerHistoryError:pass  # Sanitized status is persisted; no provider traceback.
        finally:
            with self.lock: self.pending.discard(profile_id)

    def start(self):
        if self.thread:return
        def loop():
            while not self.stop_event.is_set():
                try: self.tick()
                except Exception: pass  # Retry transient storage errors without logging credentials.
                self.stop_event.wait(1)
        self.thread = Thread(target=loop,daemon=True,name='broker-scheduler')
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=5)
        self.pool.shutdown(wait=True,cancel_futures=True)
