from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.executions import ExecutionBatch
from app.brokers.mt5_recovery_snapshot import collect, reconcile_account
from tests.test_mt5_execution_ledger import ledger, policy, order
from tests.test_mt5_execution_reconciliation import execution


@pytest.fixture
def adapter():
    account = NS(trade_mode=0, currency='USD')
    position = NS(identifier=200, symbol='XAUUSDs', type=0, volume=.1, sl=2990., tp=3020.)
    data = NS(positions=[position], orders=[], executions=[execution()])
    def forbidden(*args, **kwargs):
        pytest.fail('Recovery must not send/check orders or switch terminals')
    module = NS(ACCOUNT_TRADE_MODE_DEMO=0, ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1,
        positions_get=lambda: data.positions, orders_get=lambda: data.orders,
        symbol_info=lambda name: NS(name=name), order_send=forbidden,
        order_check=forbidden, initialize=forbidden, login=forbidden)
    value = NS(_module=module, _clock=lambda: 1800000000., _account=lambda: (account, 'a'*64),
               environment='demo', account_key='a'*64, currency='USD')
    value.read_executions = lambda _: ExecutionBatch(list(data.executions), '1800000000000',
                                                     {str(p.identifier) for p in data.positions})
    return value, data, account


def test_collects_complete_stable_canonical_evidence(adapter):
    result = collect(adapter[0])
    assert result['complete'] and not result['execution_enabled']
    assert result['executions'] == [execution()]
    assert result['open_positions']['200']['stop'] == 2990.
    assert result['pending_order_ids'] == []


@pytest.mark.parametrize('failure', ['positions', 'orders', 'live', 'identity', 'currency',
    'duplicate', 'future', 'wrong_execution_account', 'missing_symbol', 'exception', 'expired'])
def test_invalid_incomplete_or_unverified_snapshot_fails_closed(adapter, failure):
    a, data, account = adapter
    if failure == 'positions': a._module.positions_get = lambda: None
    if failure == 'orders': data.orders = None
    if failure == 'live': account.trade_mode = 2
    if failure == 'identity': a.account_key = 'c'*64
    if failure == 'currency': account.currency = 'EUR'
    if failure == 'duplicate': data.executions *= 2
    if failure == 'future': data.executions = [replace(execution(), timestamp='2040-01-01T00:00:00Z')]
    if failure == 'wrong_execution_account': data.executions = [replace(execution(), account_key='c'*64)]
    if failure == 'missing_symbol': a._module.symbol_info = lambda _: None
    if failure == 'exception':
        def broken(_): raise RuntimeError('private-secret')
        a.read_executions = broken
    if failure == 'expired':
        ticks = iter([1800000000., 1800000006.])
        a._clock = lambda: next(ticks)
    with pytest.raises(BrokerHistoryError) as exc:
        collect(a)
    assert 'private-secret' not in str(exc.value)


@pytest.mark.parametrize('change', ['fill', 'position', 'order'])
def test_concurrent_broker_changes_are_rejected(adapter, change):
    a, data, _ = adapter
    original = a.read_executions
    calls = 0
    def changing(cursor):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change == 'fill': data.executions = [replace(execution(), quantity='.05')]
            if change == 'position': data.positions[0].sl = 2980.
            if change == 'order': data.orders = [NS(ticket=88, symbol='XAUUSDs', type=2,
                                                    volume_current=.1, price_open=2900., sl=2890., tp=2910.)]
        return original(cursor)
    a.read_executions = changing
    with pytest.raises(BrokerHistoryError): collect(a)


def attempt(ledger, ticket='100'):
    p = ledger.configure(policy())
    intent = ledger.draft(p['id'], order())
    with ledger.account_guard(p['id']) as token:
        item = ledger.begin_attempt(intent['id'], guard_token=token)
        if ticket:
            ledger.record_attempt_receipt(item['id'], guard_token=token, retcode=10009, broker_order_id=ticket)
    return p, intent


def test_collector_integrates_with_receipt_bound_ledger(adapter, ledger):
    p, intent = attempt(ledger)
    result = reconcile_account(adapter[0], ledger, p['id'])
    assert result['deals_retrieved'] == 1 and result['open_positions'] == 1
    assert result['observations'][0]['decision']['state'] == 'FILLED_PROTECTED'
    assert not result['account_released']
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
    reconcile_account(adapter[0], ledger, p['id'])
    assert len(ledger.reconciliations(intent['id'])) == 1


def test_collection_failure_preserves_existing_evidence(adapter, ledger):
    p, intent = attempt(ledger)
    reconcile_account(adapter[0], ledger, p['id'])
    before = ledger.reconciliations(intent['id'])
    adapter[0]._module.positions_get = lambda: None
    with pytest.raises(BrokerHistoryError): reconcile_account(adapter[0], ledger, p['id'])
    assert ledger.reconciliations(intent['id']) == before


def test_missing_receipt_stays_unresolved(adapter, ledger):
    p, _ = attempt(ledger, None)
    assert reconcile_account(adapter[0], ledger, p['id'])['observations'][0]['decision']['state'] == 'UNRESOLVED'


def test_research_cannot_collect(adapter, ledger):
    from app.research_agent.access import preparation_scope
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(BrokerHistoryError, match='Research'): collect(adapter[0])
