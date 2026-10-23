"""Durable T01 decision diagnostics, deliberately disconnected from order APIs.

Caller supplies verified-UTC completed bars and explicitly attributed positions.
No terminal polling, broker submission, account arming or inferred fills occur.
The bounded continuous stream starts at the Asia session open; missing minutes
require a new diagnostic stream, never historical catch-up orders.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.context import StrategyContext
from app.backtesting.models import Position, EntrySignal, ManagePositionSignal, ExitSignal
from app.storage.strategy_source_archive import store
from .bars import canonical, stamp
from .deployments import digest, encoded
from .runtime import runtime_identity, serial

KEY = 'gold_ifvg_v2_skip_23et'
MAX_BARS = 2880


def implementation_identity():
    root = Path(__file__).resolve().parents[1]
    files = [Path(__file__), root/'backtesting/strategies/base.py',
             root/'forward/bars.py', root/'forward/deployments.py', root/'forward/runtime.py']
    files += sorted((root/'market_concepts').rglob('*.py'))
    return dict(runtime=runtime_identity(), dependencies={
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files})


def decide(strategy, bars, observation, symbol):
    one = pd.DataFrame(bars)
    one['timestamp'] = pd.to_datetime(one.timestamp, utc=True)
    one['available_at'] = pd.to_datetime(one.available_at, utc=True)
    grouped = one.set_index('timestamp').resample('15min')
    fifteen = grouped.agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    # A nominal 15-minute boundary cannot turn missing minutes into a full bar.
    fifteen = fifteen.loc[grouped['close'].count() == 15].reset_index()
    position = observation['position']
    if position:
        position = Position(**{**position, 'entry_time':stamp(position['entry_time'])})
    context = StrategyContext(symbol=symbol, primary_timeframe='1m',
        decision_time=stamp(bars[-1]['available_at']), frames={'1m':one, '15m':fifteen},
        position=position, equity=observation['equity'], concepts=strategy.spec.concepts)
    signal = strategy.on_bar(context)
    if signal is None:
        return None
    kinds = {EntrySignal:'entry', ManagePositionSignal:'manage', ExitSignal:'exit'}
    if type(signal) not in kinds:
        raise ValueError('Unsupported T01 decision')
    return dict(kind=kinds[type(signal)], signal=serial(asdict(signal)))


class T01DecisionRuntime:
    def __init__(self, database, registry=None):
        if registry is None:
            from app.backtesting.strategies import strategy_registry
            registry = strategy_registry
        self.database, self.registry = database, registry
        self.lock, self.cache = RLock(), {}
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_t01_diagnostics(
                id TEXT PRIMARY KEY, definition TEXT NOT NULL, definition_sha256 TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 0)''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_t01_decisions(
                deployment_id TEXT NOT NULL REFERENCES mt5_t01_diagnostics(id),
                sequence INTEGER NOT NULL, document TEXT NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(deployment_id,sequence))''')

    @staticmethod
    def _manual_only():
        from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
        MT5ExecutionLedger._manual_only()

    def prepare(self, ledger, policy_id, *, symbol, stream_key, timestamp_policy):
        self._manual_only()
        if timestamp_policy != 'verified_utc':
            raise ValueError('Verified UTC bars required; seasonal offsets are not inferred')
        if not isinstance(stream_key, str) or not 1 <= len(stream_key.strip()) <= 128:
            raise ValueError('Bounded diagnostic stream identity required')
        if ledger.database is not self.database:
            raise ValueError('Policy and diagnostic storage must match')
        with self.lock, self.registry.executing(), self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE'); ledger._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_policies WHERE id=?', (policy_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown execution policy')
            policy = json.loads(row[0])['policy']
            provenance = self.registry.provenance(KEY)
            if (policy['environment'] != 'demo' or policy['strategy_key'] != KEY
                    or policy['strategy_source_hash'] != provenance['source_sha256']
                    or symbol not in policy['symbols']):
                raise ValueError('Frozen T01 demo policy/source/symbol required')
            identifier = digest(dict(policy_id=policy_id, symbol=symbol, stream_key=stream_key))
            previous = c.execute('SELECT definition,definition_sha256 FROM mt5_t01_diagnostics WHERE id=?', (identifier,)).fetchone()
            if previous:
                if digest(json.loads(previous[0])) != previous[1]:
                    raise ValueError('T01 definition integrity failed')
                self._verify(json.loads(previous[0]))
                return dict(id=identifier, definition=json.loads(previous[0]), execution_enabled=False)
            archive = store(c, provenance, self.registry.sources())
            if archive['status'] != 'archived':
                raise ValueError('Complete T01 source identity required')
            definition = dict(mode='DIAGNOSTIC_ONLY', policy_id=policy_id,
                account_key=policy['account_key'], environment='demo', currency=policy['currency'],
                symbol=symbol, strategy_key=KEY, parameters={'direction':'both'},
                implementation=provenance, source_archive=archive,
                runtime_identity=implementation_identity(), timestamp_policy=timestamp_policy)
            c.execute('INSERT INTO mt5_t01_diagnostics VALUES(?,?,?,0)', (identifier, encoded(definition), digest(definition)))
            return dict(id=identifier, definition=definition, execution_enabled=False)

    def _verify(self, definition):
        if (definition['mode'] != 'DIAGNOSTIC_ONLY' or definition['environment'] != 'demo'
                or definition['strategy_key'] != KEY or definition['timestamp_policy'] != 'verified_utc'
                or definition['implementation'] != self.registry.provenance(KEY)
                or definition['runtime_identity'] != implementation_identity()):
            raise ValueError('Frozen T01 implementation changed; diagnostic stream cannot upgrade')

    def step(self, identifier, bar, *, observed_at, equity, position=None, attribution_verified=False):
        """One completed minute, no orders. Failed validation leaves frontier intact.

        Positions must be supplied by future receipt-bound broker orchestration.
        A flat observation means no attributed strategy position, not account flat.
        Diagnostics alone cannot be consumed as a submission authorization.
        """
        self._manual_only()
        value = canonical(bar, stamp(observed_at))
        if type(equity) not in (float, int) or not 0 < equity < float('inf'):
            raise ValueError('Finite positive observed equity required')
        observation = dict(equity=float(equity), position=serial(asdict(position)) if position else None)
        encoded(observation)
        with self.lock, self.registry.executing():
            try:
                with self.database.connect() as c:
                    row = c.execute('SELECT definition,revision,definition_sha256 FROM mt5_t01_diagnostics WHERE id=?', (identifier,)).fetchone()
                    if row is None:
                        raise ValueError('Unknown T01 diagnostic stream')
                    definition, revision = json.loads(row[0]), row[1]
                    if digest(definition) != row[2]:
                        raise ValueError('T01 definition integrity failed')
                    self._verify(definition)
                    if position is not None and (attribution_verified is not True
                            or position.symbol != definition['symbol']
                            or position.metadata.get('strategy_version') != KEY
                            or stamp(position.entry_time) > stamp(value['timestamp'])):
                        raise ValueError('Previously attributed T01 position required')
                    saved = c.execute('SELECT document,sha256 FROM mt5_t01_decisions WHERE deployment_id=? ORDER BY sequence', (identifier,)).fetchall()
                if len(saved) != revision:
                    raise ValueError('T01 durable frontier integrity failed')
                records = [json.loads(r[0]) for r in saved]
                if any(digest(record) != raw[1] for record, raw in zip(records, saved)):
                    raise ValueError('T01 decision integrity failed')
                repeated = bool(records and records[-1]['bar']['timestamp'] == value['timestamp'])
                if repeated:
                    if records[-1]['bar'] != value or records[-1]['observation'] != observation:
                        raise ValueError('Previously recorded decision inputs changed')
                if not repeated and revision >= MAX_BARS:
                    raise ValueError('Bounded diagnostic stream exhausted; no automatic continuation')
                if records and not repeated:
                    if stamp(value['timestamp']) != stamp(records[-1]['bar']['available_at']):
                        raise ValueError('Missing or out-of-order minute; no catch-up orders')
                elif not records:
                    local = stamp(value['timestamp']).astimezone(ZoneInfo('America/New_York'))
                    if (local.hour, local.minute) != (20, 0):
                        raise ValueError('Diagnostic stream must begin at 20:00 New York')
                current = self.cache.get(identifier)
                if current is None or current[0] != revision:
                    strategy = self.registry.create(KEY, **definition['parameters']); strategy.reset()
                    bars = []
                    for record in records:
                        bars.append(record['bar'])
                        if decide(strategy, bars, record['observation'], definition['symbol']) != record['result']:
                            raise ValueError('T01 restart replay diverged')
                else:
                    _, strategy, bars = current
                if repeated:
                    self.cache[identifier] = (revision, strategy, bars)
                    return records[-1]
                bars = [*bars, value]
                result = decide(strategy, bars, observation, definition['symbol'])
                record = dict(bar=value, observation=observation, result=result,
                    observed_at=stamp(observed_at).isoformat(),
                    decision_at=value['available_at'], not_before=value['available_at'],
                    mode='DIAGNOSTIC_ONLY', execution_enabled=False)
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    changed = c.execute('UPDATE mt5_t01_diagnostics SET revision=revision+1 WHERE id=? AND revision=?', (identifier, revision))
                    if changed.rowcount != 1:
                        raise ValueError('Concurrent T01 frontier changed')
                    c.execute('INSERT INTO mt5_t01_decisions VALUES(?,?,?,?)', (identifier, revision+1, encoded(record), digest(record)))
                self.cache[identifier] = (revision+1, strategy, bars)
                return record
            except Exception:
                self.cache.pop(identifier, None)
                raise
