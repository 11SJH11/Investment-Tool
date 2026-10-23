from dataclasses import replace
import json

import pandas as pd
import pytest

from app.backtesting.models import Position
from app.backtesting.strategies import strategy_registry
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from app.forward.deployments import digest, encoded
from app.forward.mt5_t01_runtime import T01DecisionRuntime, KEY
from app.storage.database import Database
from tests.test_gold_ifvg_acceptance import fixture
from tests.test_mt5_execution_ledger import policy


@pytest.fixture
def runtime(tmp_path):
    db = Database(tmp_path/'t01.db'); db.initialize()
    ledger = MT5ExecutionLedger(db)
    request = policy() | dict(strategy_key=KEY, strategy_source_hash=strategy_registry.provenance(KEY)['source_sha256'])
    p = ledger.configure(request)
    runner = T01DecisionRuntime(db)
    prepared = runner.prepare(ledger, p['id'], symbol='XAUUSDs', stream_key='fixture', timestamp_policy='verified_utc')
    return runner, prepared['id'], ledger, p


def bars(day='2026-01-04', outcome='breakeven'):
    frame = fixture(day, outcome)['1m']
    return [dict(row, timestamp=row['timestamp'].isoformat(),
                 available_at=(row['timestamp']+pd.Timedelta(minutes=1)).isoformat())
            for row in frame.to_dict('records')]


def step(runner, identifier, bar, **kwargs):
    return runner.step(identifier, bar, observed_at=bar['available_at'], equity=10000., **kwargs)


@pytest.mark.parametrize('day', ['2026-01-04', '2026-03-08', '2026-11-01'])
def test_t01_completed_confirmation_restart_idempotency_and_management(runtime, day):
    runner, identifier, _, _ = runtime
    source = bars(day)
    decisions = []
    for index, bar in enumerate(source[:60]):
        if index == 49:  # Recover consumed FVG/session state from immutable evidence.
            runner = T01DecisionRuntime(runner.database)
        decisions.append(step(runner, identifier, bar))
    assert all(d['result'] is None for d in decisions[:-1])
    entry = decisions[-1]
    assert entry['result']['kind'] == 'entry'
    signal = entry['result']['signal']
    assert signal['direction'] == 'short' and signal['stop_loss'] == 3010
    assert signal['target_r'] == 1
    assert signal['metadata']['asia_session_key'] == day
    assert entry['not_before'] == source[60]['timestamp']
    assert not entry['execution_enabled']
    assert step(runner, identifier, source[59]) == entry
    pos = Position(symbol='XAUUSDs', direction='short', entry_time=pd.Timestamp(source[60]['timestamp']),
        entry_price=3001., quantity=1., stop_loss=3010., take_profit=2992.,
        initial_risk_per_share=9., initial_risk_amount=9., metadata=signal['metadata'])
    management = step(runner, identifier, source[60], position=pos, attribution_verified=True)
    assert management['result']['kind'] == 'manage'
    assert management['result']['signal']['new_stop_loss'] == 3001
    assert management['not_before'] == source[61]['timestamp']
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0] == 61
        assert c.execute('SELECT COUNT(*) FROM mt5_execution_attempts').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM mt5_execution_intents').fetchone()[0] == 0


def test_invalid_history_does_not_advance_frontier(runtime):
    runner, identifier, _, _ = runtime; source = bars()
    with pytest.raises(ValueError, match='20:00'):
        step(runner, identifier, source[1])
    first = step(runner, identifier, source[0])
    with pytest.raises(ValueError, match='future'):
        runner.step(identifier, source[1], observed_at=source[1]['timestamp'], equity=10000.)
    with pytest.raises(ValueError, match='Missing'):
        step(runner, identifier, source[2])
    with pytest.raises(ValueError, match='changed'):
        step(runner, identifier, source[0] | dict(volume=999))
    assert step(runner, identifier, source[0]) == first
    assert step(runner, identifier, source[1])['result'] is None


def test_unknown_time_live_and_wrong_source_are_rejected(runtime):
    runner, identifier, ledger, p = runtime
    with pytest.raises(ValueError, match='Verified UTC'):
        runner.prepare(ledger, p['id'], symbol='XAUUSDs', stream_key='unknown', timestamp_policy='unverified')
    for changes in ({'environment':'live'}, {'strategy_source_hash':'c'*64}, {'strategy_key':'other'}):
        different = ledger.configure(p['policy'] | changes)
        with pytest.raises(ValueError, match='Frozen T01'):
            runner.prepare(ledger, different['id'], symbol='XAUUSDs', stream_key='wrong', timestamp_policy='verified_utc')
    assert runner.prepare(ledger, p['id'], symbol='XAUUSDs', stream_key='fixture', timestamp_policy='verified_utc')['id'] == identifier


def test_restart_rejects_changed_decision_evidence(runtime):
    runner, identifier, _, _ = runtime; source = bars()
    first = step(runner, identifier, source[0])
    with runner.database.connect() as c:
        forged = first | dict(result={'kind':'entry', 'signal':{}})
        c.execute('UPDATE mt5_t01_decisions SET document=?,sha256=?', (encoded(forged), digest(forged)))
    restarted = T01DecisionRuntime(runner.database)
    with pytest.raises(ValueError, match='replay diverged'):
        step(restarted, identifier, source[1])
    with pytest.raises(ValueError, match='replay diverged'):
        step(restarted, identifier, source[0])
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0] == 1


def test_source_and_definition_drift_fail_closed(runtime, monkeypatch):
    runner, identifier, _, _ = runtime; source = bars()
    real = runner.registry.provenance
    monkeypatch.setattr(runner.registry, 'provenance', lambda key:real(key) | dict(source_sha256='c'*64))
    with pytest.raises(ValueError, match='implementation changed'):
        step(runner, identifier, source[0])
    monkeypatch.setattr(runner.registry, 'provenance', real)
    with runner.database.connect() as c:
        definition = json.loads(c.execute('SELECT definition FROM mt5_t01_diagnostics').fetchone()[0])
        definition['symbol'] = 'OTHER'
        c.execute('UPDATE mt5_t01_diagnostics SET definition=?', (encoded(definition),))
    with pytest.raises(ValueError, match='definition integrity'):
        step(runner, identifier, source[0])


def test_unattributed_position_cannot_drive_management(runtime):
    runner, identifier, _, _ = runtime; source = bars()
    pos = Position(symbol='XAUUSDs', direction='short', entry_time=pd.Timestamp(source[0]['timestamp']),
        entry_price=3001., quantity=1., stop_loss=3010., take_profit=2992.,
        initial_risk_per_share=9., initial_risk_amount=9., metadata={'strategy_version':KEY})
    for candidate, verified in ((pos, False), (replace(pos, symbol='OTHER'), True),
                                (replace(pos, metadata={}), True)):
        with pytest.raises(ValueError, match='attributed'):
            step(runner, identifier, source[0], position=candidate, attribution_verified=verified)
    assert step(runner, identifier, source[0])['result'] is None


def test_failed_checkpoint_rolls_back_and_replays_cleanly(runtime):
    import sqlite3
    runner, identifier, _, _ = runtime; source = bars()
    for bar in source[:59]:
        step(runner, identifier, bar)
    with runner.database.connect() as c:
        c.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON mt5_t01_decisions BEGIN SELECT RAISE(ABORT,'fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):
        step(runner, identifier, source[59])
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0] == 59
        c.execute('DROP TRIGGER fail_checkpoint')
    assert step(runner, identifier, source[59])['result']['kind'] == 'entry'


def test_two_runtimes_cannot_commit_the_same_frontier_twice(runtime, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    import app.forward.mt5_t01_runtime as module
    runner, identifier, _, _ = runtime; second = T01DecisionRuntime(runner.database)
    rendezvous = Barrier(2); original = module.decide
    def synchronized(*args):
        value = original(*args); rendezvous.wait(timeout=10); return value
    monkeypatch.setattr(module, 'decide', synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(step, r, identifier, bars()[0]) for r in (runner, second)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except ValueError as e:
                assert 'Concurrent' in str(e)
    assert len(outcomes) == 1
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0] == 1
        assert c.execute('SELECT COUNT(*) FROM mt5_t01_decisions').fetchone()[0] == 1


def test_23et_first_setup_remains_excluded(runtime):
    runner, identifier, _, _ = runtime; source = bars()
    start = pd.Timestamp(source[0]['timestamp'])
    prefix = [dict(timestamp=(start+pd.Timedelta(minutes=i)).isoformat(),
        available_at=(start+pd.Timedelta(minutes=i+1)).isoformat(),
        open=3000, high=3000, low=3000, close=3000, volume=1) for i in range(120)]
    shifted = [bar | dict(timestamp=(pd.Timestamp(bar['timestamp'])+pd.Timedelta(hours=2)).isoformat(),
        available_at=(pd.Timestamp(bar['available_at'])+pd.Timedelta(hours=2)).isoformat()) for bar in source[:60]]
    results = [step(runner, identifier, bar)['result'] for bar in prefix+shifted]
    assert all(result is None for result in results)


def test_diagnostic_budget_is_bounded_without_losing_last_record(runtime, monkeypatch):
    import app.forward.mt5_t01_runtime as module
    runner, identifier, _, _ = runtime; source = bars()
    monkeypatch.setattr(module, 'MAX_BARS', 1)
    first = step(runner, identifier, source[0])
    with pytest.raises(ValueError, match='exhausted'):
        step(runner, identifier, source[1])
    assert step(runner, identifier, source[0]) == first


def test_monitor_exposes_durable_decisions_without_claiming_worker_or_trades(runtime):
    from types import SimpleNamespace
    from app.services.algo_monitoring import report
    runner, identifier, ledger, p = runtime
    source = bars(); step(runner, identifier, source[0])
    row = report(SimpleNamespace(database=runner.database))['items'][0]
    diagnostic = row['safeguards']['latest_diagnostic_stream']
    assert diagnostic['id'] == identifier and diagnostic['completed_decisions'] == 1
    assert diagnostic['last_decision_at'] == source[0]['available_at']
    assert diagnostic['mode'] == 'DIAGNOSTIC_ONLY' and not diagnostic['execution_enabled']
    assert row['last_evaluation_at'] is None and row['status'] == 'NOT_DEPLOYED'
    assert row['trades'] == [] and row['position'] is None
    second = runner.prepare(ledger, p['id'], symbol='XAUUSDs', stream_key='second', timestamp_policy='verified_utc')
    latest = report(SimpleNamespace(database=runner.database))['items'][0]['safeguards']['latest_diagnostic_stream']
    assert latest['id'] == second['id'] and latest['completed_decisions'] == 0
    assert latest['last_decision_at'] is None
