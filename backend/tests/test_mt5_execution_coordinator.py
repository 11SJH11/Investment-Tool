from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_execution_coordinator import inspect_intent
from tests.test_mt5_execution_ledger import ledger, policy, order
from tests.test_mt5_execution_preflight import context
from tests.test_mt5_order_preparation import prepared


@pytest.fixture
def gateway(ledger, prepared):
    adapter, account, terminal, symbol, quote = prepared[0]
    module = adapter._module
    for name, value in dict(SYMBOL_CALC_MODE_FOREX=0, SYMBOL_CALC_MODE_CFD=1,
        ORDER_TYPE_BUY_LIMIT=2, ORDER_TYPE_SELL_LIMIT=3, ORDER_TYPE_BUY_STOP=4,
        ORDER_TYPE_SELL_STOP=5, DEAL_TYPE_BUY=0, DEAL_TYPE_SELL=1,
        DEAL_TYPE_BALANCE=2, DEAL_TYPE_CREDIT=3).items():
        setattr(module, name, value)
    symbol.currency_profit, symbol.trade_calc_mode, symbol.trade_contract_size = 'USD', 0, 100.
    module.positions_get = lambda: []
    module.orders_get = lambda: []
    module.history_deals_get = lambda *args: []
    p = ledger.configure(policy() | {'max_gross_exposure': 100000})
    intent = ledger.draft(p['id'], order() | {'entry': 3001., 'stop': 2991., 'target': 3011.})
    return ledger, adapter, p, intent, prepared


def run(gateway, **changes):
    ledger, adapter, p, intent, _ = gateway
    return inspect_intent(adapter, ledger, p['id'], intent['id'],
        **(dict(risk_percent=1., session_key='session-1', magic=12345, deviation_points=10) | changes))


def test_composes_native_checks_and_persists_risk_without_orders(gateway):
    ledger, _, p, intent, prepared = gateway
    result = run(gateway)
    assert result['status'] == 'diagnostics_complete'
    assert not result['orders_sent'] and not result['execution_enabled']
    assessment = result['assessment']
    assert assessment['decision']['reasons'] == ['incomplete_reconciliation']
    assert assessment['proposed']['estimated_stop_risk'] == 100.
    assert assessment['proposed']['gross_exposure'] == 30010.
    assert ledger.risk_assessments(p['id']) == [assessment]
    assert ledger.intents(p['id']) == [intent]
    assert ledger.attempt(intent['id']) is None
    assert ledger.account_guard_status(p['id'])['state'] == 'IDLE'
    assert len(prepared[1]) == 1


def test_broker_rejection_does_not_invent_risk_result(gateway):
    ledger, adapter, p, intent, _ = gateway
    adapter._module.order_check = lambda _: NS(retcode=10019)
    result = run(gateway)
    assert result['status'] == 'broker_check_rejected'
    assert ledger.risk_assessments(p['id']) == []
    assert ledger.attempt(intent['id']) is None


@pytest.mark.parametrize('failure', ['live', 'account', 'future_quote', 'history', 'size'])
def test_unsafe_or_incomplete_diagnostics_fail_closed(gateway, failure):
    ledger, adapter, p, intent, prepared = gateway
    if failure == 'live': adapter.environment = 'live'
    if failure == 'account': adapter.account_key = 'c'*64
    if failure == 'future_quote': prepared[0][4].time_msc = 102000
    if failure == 'history': adapter._module.history_deals_get = lambda *args: None
    with pytest.raises((ValueError, BrokerHistoryError)):
        run(gateway, **({'risk_percent': .5} if failure == 'size' else {}))
    assert ledger.risk_assessments(p['id']) == []
    assert ledger.attempt(intent['id']) is None
    assert ledger.intents(p['id']) == [intent]
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_concurrent_account_guard_prevents_broker_checks(gateway):
    ledger, _, p, _, prepared = gateway
    with ledger.account_guard(p['id']):
        with pytest.raises(ValueError, match='busy'):
            run(gateway)
    assert prepared[1] == []


def test_research_cannot_run_diagnostics(gateway):
    from app.research_agent.access import preparation_scope
    ledger, _, _, _, prepared = gateway
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(ValueError, match='Research'):
            run(gateway)
    assert prepared[1] == []


def test_preparation_expiring_during_observation_is_rejected(gateway):
    ledger, adapter, p, _, _ = gateway
    calls = 0
    def history(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            adapter._clock = lambda: 106.
        return []
    adapter._module.history_deals_get = history
    with pytest.raises(BrokerHistoryError, match='expired'):
        run(gateway)
    assert ledger.risk_assessments(p['id']) == []


def test_manual_positions_consume_account_risk(gateway):
    ledger, adapter, p, _, _ = gateway
    position = NS(ticket=77, symbol='XAUUSDs', type=0, volume=.1,
                  sl=2990., tp=3020., swap=-2., profit=-150.)
    adapter._module.positions_get = lambda: [position]
    result = run(gateway)
    facts = result['assessment']['facts']
    assert facts['open_positions'] == 1
    assert facts['floating_losses'] == 152.
    assert facts['remaining_stop_risk'] == 100.
    assert 'daily_loss_budget' in result['assessment']['decision']['reasons']
    assert ledger.risk_assessments(p['id'])[0]['facts'] == facts


def test_other_strategy_uncertainty_is_counted_from_durable_ledger(gateway):
    ledger, _, p, _, _ = gateway
    other = ledger.configure(policy() | {'strategy_key': 'other'})
    draft = ledger.draft(other['id'], order())
    with ledger.account_guard(other['id']) as token:
        ledger.begin_attempt(draft['id'], guard_token=token)
    # Fixture-only guard removal to exercise independent durable evidence checks.
    with ledger.database.connect() as c:
        c.execute('DELETE FROM mt5_execution_account_guards')
    result = run(gateway)
    assert result['assessment']['facts']['unresolved_submissions'] == 1
    assert result['assessment']['facts']['session_entries'] == 0
    assert 'uncertain_submission' in result['assessment']['decision']['reasons']
