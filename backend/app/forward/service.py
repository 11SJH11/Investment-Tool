"""Backend-owned IEX shadow preparation/polling; no browser-owned timer or orders."""
from datetime import datetime, timedelta, timezone
import json
from threading import Event, Thread, RLock
from .alpaca_data import AlpacaForwardData
from .bars import BarLog, stamp
from .deployments import Deployments, encoded
from .runtime import ShadowRuntime, WARMUP_SESSIONS


class ForwardService:
    def __init__(self,database,settings,*,provider=None,start_thread=True,clock=lambda:datetime.now(timezone.utc)):
        self.database=database;self.clock=clock;self.lock=RLock();self.stop=Event()
        self.deployments=Deployments(database);self.runtime=ShadowRuntime(database)
        self.runtime.bars=BarLog(database,clock)
        from .paper_service import PaperService
        self.paper=PaperService(database,settings,self.runtime,start_thread=start_thread,clock=clock)
        self.provider=provider
        if provider is None and settings.alpaca_configured:
            self.provider=AlpacaForwardData(settings.alpaca_api_key,settings.alpaca_api_secret)
        self.next_poll=0
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_preparations(
                experiment_id TEXT PRIMARY KEY,status TEXT NOT NULL,error TEXT,
                FOREIGN KEY(experiment_id) REFERENCES forward_experiments(id))''')
            c.execute("UPDATE forward_preparations SET status='FAILED',error='Preparation interrupted; create a new experiment' WHERE status='PREPARING'")
        self.thread=None
        if start_thread:
            self.thread=Thread(target=self._loop,name='forward-shadows',daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        self.paper.close()
        if self.thread:self.thread.join(timeout=25)
        if self.provider:self.provider.close()

    def _loop(self):
        while not self.stop.wait(15):
            try:self.tick()
            except Exception:pass  # Individual failures are durably reported below.

    def prepare(self,request_key,account):
        if self.provider is None:raise ValueError('Configure Alpaca credentials before preparing IEX shadows')
        with self.lock:
            rows=self.deployments.prepare(request_key,account)
            experiment=rows[0]['experiment_id']
            with self.database.connect() as c:
                c.execute("INSERT OR IGNORE INTO forward_preparations VALUES (?,'QUEUED',NULL)",(experiment,))
            return self.report(experiment)

    def _prepare(self,experiment):
        current=stamp(self.clock())
        schedule=self.provider.calendar((current-timedelta(days=180)).date(),(current+timedelta(days=90)).date())
        past=[s for s in schedule if stamp(s['close'])<=current]
        if len(past)<WARMUP_SESSIONS:raise ValueError('Provider calendar has insufficient warmup sessions')
        start=stamp(past[-WARMUP_SESSIONS]['open'])
        schedule=[s for s in schedule if stamp(s['open'])>=start]
        self.runtime.bars.bind(experiment,provider='alpaca',feed='iex',sessions=schedule)
        bars=self.provider.bars(start,current-timedelta(seconds=5))
        bars=self._regular(bars,schedule)
        self.runtime.bars.append(experiment,bars)
        self.runtime.activate(experiment)

    @staticmethod
    def _regular(bars,sessions):
        return [b for b in bars if any(stamp(s['open'])<=stamp(b['timestamp'])<stamp(s['close']) for s in sessions)]

    def tick(self):
        if self.provider is None or self.stop.is_set():return
        with self.lock:
            current=stamp(self.clock())
            if current.timestamp()<self.next_poll:return
            self.next_poll=current.timestamp()+15
            with self.database.connect() as c:
                plans=[dict(r) for r in c.execute('SELECT * FROM forward_preparations')]
            for plan in plans:
                experiment=plan['experiment_id']
                try:
                    if plan['status']=='QUEUED':
                        with self.database.connect() as c:c.execute("UPDATE forward_preparations SET status='PREPARING' WHERE experiment_id=?",(experiment,))
                        self._prepare(experiment)
                        with self.database.connect() as c:c.execute("UPDATE forward_preparations SET status='READY',error=NULL WHERE experiment_id=?",(experiment,))
                    elif plan['status']=='READY':
                        rows=self.deployments.list(experiment)
                        if not any(r['state']['status']=='ACTIVE' for r in rows):continue
                        feed,bars=self.runtime.bars.read(experiment);sessions=json.loads(feed['sessions_json'])
                        if not bars:raise ValueError('Warmup history missing')
                        cutoff=current-timedelta(seconds=5)
                        latest=stamp(bars[-1]['timestamp'])
                        incoming=self.provider.bars(latest,cutoff) if latest<cutoff else []
                        incoming=self._regular(incoming,sessions)
                        active=next((s for s in sessions if stamp(s['open'])+timedelta(seconds=95)<current<=stamp(s['close'])+timedelta(seconds=95)),None)
                        newest=stamp((incoming or bars)[-1]['available_at'])
                        if active and current-newest>timedelta(seconds=95):raise ValueError('IEX completed bars are stale; shadows halted')
                        self.runtime.ingest(experiment,incoming)
                except Exception as exc:
                    self.runtime.halt(experiment,'forward_data_or_runtime_failure')
                    # Only our validated ValueError text is UI-safe; provider bodies never are.
                    reason=str(exc) if isinstance(exc,ValueError) else 'Forward provider request failed; check credentials, entitlement and data coverage'
                    with self.database.connect() as c:
                        c.execute("UPDATE forward_preparations SET status='FAILED',error=? WHERE experiment_id=?",(reason,experiment))
                    retry=getattr(exc,'retry_after',None)
                    if retry:self.next_poll=max(self.next_poll,current.timestamp()+min(3600,max(15,retry)))

    def halt(self,experiment):
        with self.lock:
            with self.database.connect() as c:
                c.execute("UPDATE forward_preparations SET status='STOPPED',error=NULL WHERE experiment_id=?",(experiment,))
            self.runtime.halt(experiment,'user_disarmed_shadow')
        return self.report(experiment)

    def report(self,experiment=None):
        with self.database.connect() as c:
            identifiers=[experiment] if experiment else [r[0] for r in c.execute('SELECT id FROM forward_experiments ORDER BY created_at DESC')]
            reports=[]
            for identifier in identifiers:
                row=c.execute('SELECT * FROM forward_preparations WHERE experiment_id=?',(identifier,)).fetchone()
                deployments=self.deployments._list(c,identifier)
                for d in deployments:
                    d['state']['trade_count']=len(d['state']['trade_history'])
                    d['state']['trade_history']=d['state']['trade_history'][-100:]
                reports.append(dict(id=identifier,preparation=dict(row) if row else None,deployments=deployments))
        return dict(configured=self.provider is not None,provider='alpaca',feed='iex',adjustment='raw',items=reports,
                    limitation='IEX-only coverage. Missing/revised minutes halt; no synthetic candles. Independent shadow accounts, no broker orders.')
