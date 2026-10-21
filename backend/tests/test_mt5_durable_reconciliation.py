from dataclasses import replace

import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger, policy, order
from tests.test_mt5_execution_reconciliation import execution


def record(ledger, intent, fills=None, positions=None, **changes):
    return ledger.record_reconciliation(intent['id'],
        [execution()] if fills is None else fills,
        {'200': dict(symbol='XAUUSDs', side='buy', quantity_lots=.1, stop=2990, target=3020)}
        if positions is None else positions,
        **(dict(broker_order_id='100', account_key='a'*64, environment='demo',
                complete=True, observed_at_ms=1792497600000) | changes))


def setup(ledger):
    p = ledger.configure(policy())
    return p, ledger.draft(p['id'], order())


def test_duplicate_observation_and_restart_preserve_evidence_without_arming(ledger):
    p, intent = setup(ledger)
    first = record(ledger, intent)
    assert first == record(ledger, intent)
    assert first['decision']['state'] == 'FILLED_PROTECTED'
    assert not first['attribution_verified'] and not first['execution_enabled']
    assert ledger.intents(p['id']) == [intent]
    restarted = MT5ExecutionLedger(ledger.database)
    assert restarted.reconciliations(intent['id']) == [first]
    assert not restarted.policies()[0]['enabled']
    with pytest.raises(ValueError, match='superseded'):
        record(ledger, intent)
    with pytest.raises(ValueError, match='disabled'):
        restarted.authorize_submission(intent['id'])


def test_partial_close_then_complete_history_retained(ledger):
    _, intent = setup(ledger)
    half = replace(execution('2'), order_id='101', role='exit', side='sell', quantity='.05')
    position = dict(symbol='XAUUSDs', side='buy', quantity_lots=.05, stop=2990, target=3020)
    first = record(ledger, intent, [execution(), half], {'200': position})
    final = record(ledger, intent, [execution(), half, replace(half, external_id='3')], {},
                   observed_at_ms=1792497601000)
    assert first['decision']['remaining_lots'] == '0.05'
    assert final['decision']['state'] == 'CLOSED'
    assert ledger.reconciliations(intent['id']) == [final, first]
    assert ledger.reconciliations(intent['id'], limit=1) == [final]


@pytest.mark.parametrize('changes,state', [
    ({'complete': False}, 'UNRESOLVED'),
    ({'broker_order_id': None}, 'UNRESOLVED'),
    ({'environment': 'live'}, 'IDENTITY_CONFLICT'),
    ({'account_key': 'c'*64}, 'IDENTITY_CONFLICT'),
])
def test_incomplete_or_conflicting_evidence_never_clears_guard(ledger, changes, state):
    p, intent = setup(ledger)
    with pytest.raises(RuntimeError):
        with ledger.account_guard(p['id']):
            raise RuntimeError('simulated interruption')
    observation = record(ledger, intent, **changes)
    assert observation['decision']['state'] == state
    assert not observation['decision']['retry_allowed']
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
    # Even a later positive observation cannot release account-wide uncertainty.
    record(ledger, intent)
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_duplicate_fills_are_conflict_not_duplicate_import(ledger):
    _, intent = setup(ledger)
    result = record(ledger, intent, [execution(), execution()])
    assert result['decision']['state'] == 'EVIDENCE_CONFLICT'
    assert len(ledger.reconciliations(intent['id'])) == 1


def test_provider_metadata_is_not_copied_to_observation_log(ledger):
    _, intent = setup(ledger)
    record(ledger, intent, [replace(execution(), metadata={'comment': 'private-native-text'})])
    assert 'private-native-text' not in str(ledger.reconciliations(intent['id']))


@pytest.mark.parametrize('changes', [
    {'observed_at_ms': True}, {'observed_at_ms': 0},
    {'broker_order_id': 'private-native-error'}, {'broker_order_id': '0'},
    {'broker_order_id': '1'*21},
])
def test_invalid_observation_not_persisted(ledger, changes):
    _, intent = setup(ledger)
    with pytest.raises(ValueError):
        record(ledger, intent, **changes)
    assert ledger.reconciliations(intent['id']) == []


def test_research_cannot_write_reconciliation(ledger):
    from app.research_agent.access import preparation_scope
    _, intent = setup(ledger)
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(ValueError, match='Research'):
            record(ledger, intent)
    assert ledger.reconciliations(intent['id']) == []


def test_unknown_intent_and_invalid_read_limit(ledger):
    with pytest.raises(ValueError, match='Unknown'):
        record(ledger, {'id': 'missing'})
    for limit in (0, True, 1001):
        with pytest.raises(ValueError):
            ledger.reconciliations('missing', limit=limit)
