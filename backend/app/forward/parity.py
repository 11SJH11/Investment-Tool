"""Independent completed-session replay against immutable shadow evidence."""
import json
from threading import Lock
from zoneinfo import ZoneInfo

from app.backtesting.engine import BacktestEngine
from app.backtesting.incremental import IncrementalState
from app.backtesting.models import BacktestConfig
from .bars import stamp
from .deployments import digest, encoded, now


class SessionParity:
    def __init__(self, runtime):
        self.runtime=runtime; self.lock=Lock()
        with runtime.database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_session_parity(
                experiment_id TEXT NOT NULL,session_date TEXT NOT NULL,document TEXT NOT NULL,
                PRIMARY KEY(experiment_id,session_date))''')

    def reports(self, connection, experiment):
        return [json.loads(r[0]) for r in connection.execute(
            'SELECT document FROM forward_session_parity WHERE experiment_id=? ORDER BY session_date DESC',(experiment,))]

    def run(self, experiment, session_date):
        if not self.lock.acquire(blocking=False):
            raise ValueError('A session replay is already running')
        try:
            # Freeze the bar prefix and loaded registry generation. New runtime
            # instances are used; no live engine/strategy state is reset or reused.
            with self.runtime.registry.executing():
                with self.runtime.lock:
                    feed,frame,start,closes=self.runtime._history(experiment)
                    sessions=json.loads(feed['sessions_json'])
                    session=next((s for s in sessions if str(stamp(s['open']).astimezone(ZoneInfo('America/New_York')).date())==session_date),None)
                    if not session or stamp(session['close'])>stamp(self.runtime.bars.clock()) or stamp(session['close'])<=start:
                        raise ValueError('Choose a completed forward provider session')
                    end=stamp(session['close'])
                    frame=frame.loc[frame.available_at<=end].copy()
                    if frame.empty or frame.available_at.iloc[-1]!=end:
                        raise ValueError('Session close bar is unavailable')
                    rows=self.runtime.deployments.list(experiment)
                    for row in rows:self.runtime._verify(row)
                results=[]
                for row in rows:
                    definition=row['definition']
                    current=(BacktestEngine(BacktestConfig(**definition['engine'])),
                             self.runtime.registry.create(definition['strategy_key'],**definition['parameters']),IncrementalState(closes))
                    replay=self.runtime._run(current,frame,start)
                    evidence=self.runtime._evidence(current,replay)
                    with self.runtime.database.connect() as c:
                        saved=c.execute('SELECT evidence_json,sha256 FROM forward_checkpoints WHERE deployment_id=? AND decision_at=?',
                                        (row['id'],end.isoformat())).fetchone()
                    original=json.loads(saved[0]) if saved else None
                    integrity=bool(saved and digest(original)==saved[1])
                    checks={key:bool(integrity and original.get(key)==evidence[key])
                            for key in ('trade_sha256','setup_sha256','engine','equity_point')}
                    results.append(dict(deployment_id=row['id'],name=row['name'],
                        status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
                        recorded_sha256=saved[1] if saved else None,replayed_sha256=digest(evidence)))
                report=dict(session_date=session_date,checked_at=now(),status='PASS' if all(r['status']=='PASS' for r in results) else 'FAIL',
                            through=end.isoformat(),results=results,
                            note='Independent replay of the immutable prefix through this session close. Cumulative setup/trade hashes, final engine state and marked equity must match. Broker fills are excluded.')
                with self.runtime.database.connect() as c:
                    c.execute('INSERT INTO forward_session_parity VALUES (?,?,?) ON CONFLICT(experiment_id,session_date) DO UPDATE SET document=excluded.document',
                              (experiment,session_date,encoded(report)))
                return report
        finally:self.lock.release()
