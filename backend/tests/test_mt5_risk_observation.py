from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_risk_observation import observe
from app.brokers.mt5_execution_risk import assess
from tests.test_mt5_execution_ledger import policy

NOW = 1792411200000


@pytest.fixture
def context():
    account = NS(trade_mode=0, currency='USD', equity=10000., margin_free=5000.)
    position = NS(ticket=1, symbol='XAUUSDs', type=0, volume=.1, sl=2990., tp=3020., swap=-2., profit=-50.)
    order = NS(ticket=2, symbol='XAUUSDs', type=2, volume_current=.1, price_open=2980., sl=2970., tp=2990.)
    deal = NS(ticket=3, type=0, time_msc=NOW-1000, profit=-20., commission=-1., swap=-2., fee=-3.)
    data = NS(positions=[position], orders=[order], deals=[deal])
    symbol = NS(name='XAUUSDs', currency_profit='USD', trade_calc_mode=0, trade_contract_size=100.)
    quote = NS(time_msc=NOW, bid=3000., ask=3001.)
    def forbidden(*args, **kwargs):
        pytest.fail('Observation must never invoke orders')
    module = NS(ACCOUNT_TRADE_MODE_DEMO=0, SYMBOL_CALC_MODE_FOREX=0, SYMBOL_CALC_MODE_CFD=1,
        ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1, ORDER_TYPE_BUY_LIMIT=2, ORDER_TYPE_SELL_LIMIT=3,
        ORDER_TYPE_BUY_STOP=4, ORDER_TYPE_SELL_STOP=5,
        DEAL_TYPE_BUY=0, DEAL_TYPE_SELL=1, DEAL_TYPE_BALANCE=2, DEAL_TYPE_CREDIT=3,
        positions_get=lambda: data.positions, orders_get=lambda: data.orders,
        history_deals_get=lambda *a: data.deals, symbol_info=lambda _: symbol,
        symbol_info_tick=lambda _: quote, order_send=forbidden, order_check=forbidden,
        order_calc_profit=lambda side, symbol, lots, entry, stop: (stop-entry)*(1 if side == 0 else -1)*lots*100)
    adapter = NS(environment='demo', currency='USD', account_key='a'*64, _module=module,
                 _account=lambda: (account, 'a'*64), _clock=lambda: NOW/1000)
    return adapter, data, account, symbol, quote


def run(context):
    return observe(context[0], strategy_key='fixture', session_key='session-1',
                   session_entries=0, unresolved_submissions=0)


def test_account_wide_native_observation_includes_costs_and_pending(context):
    result = run(context)
    assert result['gross_exposure'] == 30010
    assert result['pending_gross_exposure'] == 29800
    assert result['remaining_stop_risk'] == result['pending_stop_risk'] == 100
    assert result['realized_losses_today'] == 26
    assert result['floating_losses'] == 52
    assert result['complete'] and not result['reconciled']
    assert result['open_positions'] == result['pending_entries'] == 1
    evaluation = assess(policy(), result, dict(symbol='XAUUSDs', estimated_stop_risk=10.,
                         estimated_margin=100., gross_exposure=100.), now_ms=NOW, session_key='session-1')
    assert not evaluation['allowed'] and 'incomplete_reconciliation' in evaluation['reasons']


def test_short_valuation_and_empty_account(context):
    p = context[1].positions[0]
    p.type, p.sl = 1, 3011.
    assert run(context)['remaining_stop_risk'] == 100
    context[1].positions = []; context[1].orders = []; context[1].deals = []
    result = run(context)
    assert result['gross_exposure'] == result['remaining_stop_risk'] == result['realized_losses_today'] == 0


@pytest.mark.parametrize('field', ['positions', 'orders', 'deals'])
def test_missing_or_duplicate_history_is_not_empty(context, field):
    original = getattr(context[1], field)
    setattr(context[1], field, None)
    with pytest.raises(BrokerHistoryError): run(context)
    setattr(context[1], field, original+original)
    with pytest.raises(BrokerHistoryError): run(context)


@pytest.mark.parametrize('index,field,value', [
    (0, 'environment', 'live'), (0, 'account_key', 'b'*64), (2, 'trade_mode', 2),
    (2, 'currency', 'EUR'), (2, 'margin_free', -1.),
    (3, 'currency_profit', 'EUR'), (3, 'trade_calc_mode', 99), (3, 'trade_contract_size', 0.),
    (4, 'time_msc', NOW-5001), (4, 'time_msc', NOW+1), (4, 'ask', 2999.),
])
def test_unsupported_or_stale_valuation_fails_closed(context, index, field, value):
    setattr(context[index], field, value)
    with pytest.raises(BrokerHistoryError): run(context)


@pytest.mark.parametrize('collection,field,value', [
    ('positions', 'sl', 0.), ('positions', 'sl', 3001.), ('positions', 'volume', -1.),
    ('positions', 'profit', float('nan')), ('orders', 'type', 6), ('orders', 'sl', 0.),
    ('orders', 'volume_current', 0.), ('deals', 'time_msc', NOW+1), ('deals', 'type', 99),
])
def test_bad_broker_facts(context, collection, field, value):
    setattr(getattr(context[1], collection)[0], field, value)
    with pytest.raises(BrokerHistoryError): run(context)


def test_profit_does_not_replenish_budget_and_withdrawal_not_trade_loss(context):
    d = context[1].deals[0]
    d.profit = 100.
    assert run(context)['realized_losses_today'] == 6
    d.type, d.profit = 2, -1000.
    assert run(context)['realized_losses_today'] == 6


@pytest.mark.parametrize('collection', ['positions', 'orders', 'deals'])
def test_structural_change_during_read_rejected(context, collection):
    module = context[0]._module
    method = {'positions': 'positions_get', 'orders': 'orders_get', 'deals': 'history_deals_get'}[collection]
    calls = 0
    original = getattr(context[1], collection)
    def changing(*args):
        nonlocal calls
        calls += 1
        return original if calls == 1 else []
    setattr(module, method, changing)
    with pytest.raises(BrokerHistoryError): run(context)


@pytest.mark.parametrize('value', [None, 10., float('nan')])
def test_failed_or_wrong_sign_stop_calculation_rejected(context, value):
    context[0]._module.order_calc_profit = lambda *a: value
    with pytest.raises(BrokerHistoryError): run(context)


def test_provider_exception_sanitized(context):
    def fail(*a): raise RuntimeError('secret-password')
    context[0]._module.history_deals_get = fail
    with pytest.raises(BrokerHistoryError) as e: run(context)
    assert 'secret-password' not in str(e.value)


def test_slow_observation_and_changed_account_rejected(context):
    ticks = iter([NOW/1000, NOW/1000+6])
    context[0]._clock = lambda: next(ticks)
    with pytest.raises(BrokerHistoryError): run(context)
    context[0]._clock = lambda: NOW/1000
    calls = 0
    def changed():
        nonlocal calls
        calls += 1
        return context[2], 'a'*64 if calls == 1 else 'b'*64
    context[0]._account = changed
    with pytest.raises(BrokerHistoryError): run(context)
