"""Independent shadow runtimes with durable evidence and replay-based recovery.

Only the four trusted registered frozen strategies are eligible. Archive bytes
are never executed. Source/runtime drift halts instead of silently upgrading.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from threading import RLock
from zoneinfo import ZoneInfo

import pandas as pd
from app.backtesting.engine import BacktestEngine
from app.backtesting.incremental import IncrementalState
from app.backtesting.models import BacktestConfig
from .bars import BarLog, stamp
from .deployments import Deployments, STRATEGIES, digest, encoded

WARMUP_SESSIONS = 60


def runtime_identity():
    root=Path(__file__).resolve().parents[1]
    return dict(python=sys.version,pandas=pd.__version__,files={name:sha256((root/name).read_bytes()).hexdigest()
        for name in ('backtesting/engine.py','backtesting/models.py','backtesting/context.py','backtesting/incremental.py')})


def serial(value):
    if isinstance(value,dict):return {str(k):serial(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [serial(v) for v in value]
    if isinstance(value,datetime):return value.isoformat()
    return value


class ShadowRuntime:
    def __init__(self,database,registry=None):
        self.database=database;self.deployments=Deployments(database);self.bars=BarLog(database)
        if registry is None:
            from app.backtesting.strategies import strategy_registry
            registry=strategy_registry
        self.registry=registry;self.lock=RLock();self.instances={}
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_checkpoints(
                deployment_id TEXT NOT NULL, decision_at TEXT NOT NULL,
                evidence_json TEXT NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(deployment_id,decision_at),
                FOREIGN KEY(deployment_id) REFERENCES forward_deployments(id))''')

    def _history(self,experiment):
        feed,rows=self.bars.read(experiment)
        start=stamp(feed['start_at']);sessions=json.loads(feed['sessions_json'])
        historical=[s for s in sessions if stamp(s['close'])<=start]
        if len(historical)<WARMUP_SESSIONS:
            raise ValueError('At least 60 complete provider sessions of minute warmup are required')
        observed={r['timestamp'] for r in rows}
        for s in historical[-WARMUP_SESSIONS:]:
            expected=pd.date_range(s['open'],s['close'],freq='min',inclusive='left')
            if any(t.isoformat() not in observed for t in expected):
                raise ValueError('Required warmup history is incomplete')
        frame=pd.DataFrame(rows)
        if not frame.empty:
            frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
            frame['available_at']=pd.to_datetime(frame.available_at,utc=True)
        closes={stamp(s['open']).astimezone(ZoneInfo('America/New_York')).date():stamp(s['close']) for s in sessions}
        return feed,frame,start,closes

    def activate(self,experiment):
        """Internal shadow-only activation after feed/history validation. No broker arm."""
        with self.lock, self.registry.executing():
            feed,_,_,_=self._history(experiment)
            rows=self.deployments.list(experiment)
            if len(rows)!=4:raise ValueError('All four independent deployments are required')
            for row in rows:
                self._verify(row)
                if row['state']['status']!='DRAFT':raise ValueError('Only drafts may be activated')
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                for row in rows:
                    state={**row['state'],'status':'ACTIVE','started_at':datetime.now(timezone.utc).isoformat(),
                           'future_oos_started_at':feed['start_at'],'runtime_identity':runtime_identity()}
                    updated=c.execute('UPDATE forward_deployments SET state_json=?,revision=revision+1 WHERE id=? AND revision=?',
                        (encoded(state),row['id'],row['revision']))
                    if updated.rowcount!=1:raise ValueError('Deployment changed during activation')
            return self.deployments.list(experiment)

    def _verify(self,row):
        definition=row['definition'];key=definition['strategy_key']
        if key not in STRATEGIES.values() or definition['mode']!='SHADOW':
            raise ValueError('Only the frozen shadow strategy family is supported')
        self.deployments.verify_sources(row['id'])
        if self.registry.provenance(key)!=definition['implementation']:
            raise ValueError('Loaded strategy changed; frozen shadow cannot silently upgrade')
        if row['state'].get('runtime_identity',runtime_identity())!=runtime_identity():
            raise ValueError('Engine/runtime changed; shadow must be reconciled')

    def halt(self,experiment,category='shadow_runtime_failure'):
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in self.deployments._list(c,experiment):
                if row['state']['status']=='ACTIVE':
                    state={**row['state'],'status':'HALTED','last_error_category':category,'execution_enabled':False}
                    c.execute('UPDATE forward_deployments SET state_json=?,revision=revision+1 WHERE id=?', (encoded(state),row['id']))
                self.instances.pop(row['id'],None)

    def tick(self,experiment):
        with self.lock, self.registry.executing():
            try:
                feed,frame,start,closes=self._history(experiment)
                rows=self.deployments.list(experiment)
                for row in rows:
                    if row['state']['status']!='ACTIVE':continue
                    self._verify(row)
                    if frame.empty or not (frame.timestamp>=start).any():continue
                    self._advance(row,frame,start,closes)
                return self.deployments.list(experiment)
            except Exception:
                self.instances.clear()
                self.halt(experiment)
                raise

    def ingest(self,experiment,bars):
        with self.lock:
            try:
                self.bars.append(experiment,bars)
                return self.tick(experiment)
            except Exception:
                self.halt(experiment,'market_data_or_runtime_failure')
                raise

    def _advance(self,row,frame,start,closes):
        identifier=row['id'];definition=row['definition'];cursor=row['state']['last_evaluated_decision_at']
        current=self.instances.get(identifier)
        if current is None:
            strategy=self.registry.create(definition['strategy_key'],**definition['parameters'])
            current=(BacktestEngine(BacktestConfig(**definition['engine'])),strategy,IncrementalState(closes))
            self.instances[identifier]=current
            if cursor:
                previous=frame.loc[frame.available_at<=stamp(cursor)]
                replayed=self._run(current,previous,start)
                evidence=self._evidence(current,replayed)
                with self.database.connect() as c:
                    saved=c.execute('SELECT evidence_json,sha256 FROM forward_checkpoints WHERE deployment_id=? AND decision_at=?',(identifier,cursor)).fetchone()
                if not saved or digest(json.loads(saved[0]))!=saved[1] or digest(evidence)!=saved[1]:
                    raise ValueError('Shadow restart replay diverged from durable evidence')
        new=frame.loc[(frame.timestamp>=start)&(frame.available_at>stamp(cursor) if cursor else True)]
        for _,bar in new.iterrows():
            available=bar.available_at.isoformat()
            visible=frame.loc[frame.available_at<=bar.available_at]
            result=self._run(current,visible,start)
            evidence=self._evidence(current,result)
            state={**row['state'],'last_evaluated_decision_at':available,
                   'equity':result['equity_curve'][-1]['equity'],
                   'trade_history':result['trades'],'position':evidence['engine']['positions'].get('QQQ'),
                   'pending':{'entries':evidence['engine']['pending_entries'],'exits':evidence['engine']['pending_exits']},
                   'daily_state':evidence['engine']['entries_by_day'],
                   'trades_today':evidence['engine']['entries_by_day'].get(str(bar.timestamp.tz_convert('America/New_York').date()),0),
                   'strategy_state':{'recovery':'replay_immutable_completed_bars','through':available}}
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                changed=c.execute('UPDATE forward_deployments SET state_json=?,revision=revision+1 WHERE id=? AND revision=?',
                                  (encoded(state),identifier,row['revision']))
                if changed.rowcount!=1:raise ValueError('Concurrent shadow checkpoint changed')
                c.execute('INSERT INTO forward_checkpoints VALUES (?,?,?,?)',(identifier,available,encoded(evidence),digest(evidence)))
            row['revision']+=1;row['state']=state

    @staticmethod
    def _run(current,frame,start):
        engine,strategy,state=current
        # The log requires availability == start + exactly one minute. Preserve
        # the frozen Alpaca backtest OHLCV contract; the engine's native 1m
        # completion calculation is identical, without delayed-bar fill rules.
        native=frame.drop(columns=['available_at'])
        from app.services.chart_data import prepare_chart_bars
        frames={'1m':native}
        for tf in strategy.spec.timeframes:
            if tf=='1m':continue
            if tf!='15m':raise ValueError('Unsupported frozen forward timeframe')
            frames[tf]=prepare_chart_bars(native,tf,'regular')[0]
        return engine.run(symbol_frames={'QQQ':frames},strategies={'QQQ':strategy},
                          primary_timeframe='1m',evaluation_start=start,incremental=state)

    @staticmethod
    def _evidence(current,result):
        # Store one equity observation, not another copy of the growing curve.
        # Cumulative trade/setup hashes still detect recovery divergence.
        return serial(dict(engine=current[2].snapshot(),
                           trade_sha256=digest(serial(result['trades'])),
                           setup_sha256=digest(serial(result['setups'])),
                           equity_point=result['equity_curve'][-1]))
