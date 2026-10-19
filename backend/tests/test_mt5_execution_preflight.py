from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_execution_preflight import preflight


@pytest.fixture
def context():
    account = NS(trade_mode=0, currency='USD', equity=10000, balance=10000,
                 margin_free=5000, trade_allowed=True, trade_expert=True)
    terminal = NS(connected=True, trade_allowed=True, tradeapi_disabled=False)
    symbol = NS(name='XAUUSDs', trade_mode=4, order_mode=49, trade_tick_size=.01,
                trade_stops_level=50, point=.01, volume_min=.01, volume_max=50, volume_step=.01)
    quote = NS(bid=3000., ask=3001., time_msc=100000)
    def forbidden(*args, **kwargs):
        pytest.fail('Read-only preflight must never call order operations')
    module = NS(ACCOUNT_TRADE_MODE_DEMO=0, SYMBOL_TRADE_MODE_FULL=4,
                SYMBOL_TRADE_MODE_LONGONLY=1, SYMBOL_TRADE_MODE_SHORTONLY=2,
                SYMBOL_ORDER_MARKET=1, SYMBOL_ORDER_SL=16, SYMBOL_ORDER_TP=32,
                ORDER_TYPE_BUY=0, ORDER_TYPE_SELL=1,
                terminal_info=lambda: terminal, symbol_info=lambda _: symbol,
                symbol_info_tick=lambda _: quote, order_send=forbidden, order_check=forbidden,
                order_calc_profit=lambda side, symbol, lots, entry, stop:
                    (stop-entry)*(1 if side == 0 else -1)*lots*100,
                order_calc_margin=lambda *args: args[2]*1000)
    adapter = NS(environment='demo', currency='USD', account_key='a'*64,
                 _module=module, _account=lambda: (account, 'a'*64))
    return adapter, account, terminal, symbol, quote


def request(**changes):
    return dict(symbol='XAUUSDs', side='buy', stop=2991., target=3011., risk_percent=1.) | changes


@pytest.mark.parametrize('side,stop,target,entry,lots', [
    ('buy', 2991., 3011., 3001., .1), ('sell', 3010., 2990., 3000., .1)])
def test_executable_side_and_equity_sizing(context, side, stop, target, entry, lots):
    result = preflight(context[0], request(side=side, stop=stop, target=target), now_ms=101000)
    assert result['sizing']['entry'] == entry
    assert result['sizing']['quantity_lots'] == lots
    assert result['sizing']['actual_estimated_risk'] == 100
    assert not result['execution_enabled']
    assert 'durable_authorization' in result['remaining_gates']


@pytest.mark.parametrize('object_index,field,value', [
    (0, 'environment', 'live'), (0, 'account_key', 'b'*64),
    (1, 'trade_mode', 2), (1, 'trade_mode', 1), (1, 'currency', 'EUR'),
    (1, 'trade_allowed', False), (1, 'trade_expert', False),
    (2, 'connected', False), (2, 'tradeapi_disabled', True), (2, 'trade_allowed', False),
    (3, 'trade_mode', 0), (3, 'trade_mode', 3), (3, 'trade_mode', 2),
    (3, 'order_mode', 1), (3, 'trade_stops_level', -1),
    (4, 'time_msc', 90000), (4, 'time_msc', 102000), (4, 'ask', 2999),
    (4, 'bid', float('nan')), (4, 'ask', 0), (1, 'margin_free', 1),
])
def test_unsafe_terminal_facts_fail_closed(context, object_index, field, value):
    setattr(context[object_index], field, value)
    with pytest.raises(BrokerHistoryError):
        preflight(context[0], request(), now_ms=101000)


@pytest.mark.parametrize('changes', [
    {'stop': 3000.5},  # Below ask but above bid: invalid protection.
    {'stop': 2999.75}, {'target': 3000.5}, {'target': 3011.005},
    {'risk_percent': .001}, {'risk_percent': float('nan')}, {'submit': True},
])
def test_bad_request_and_minimum_lot_rejected(context, changes):
    with pytest.raises(BrokerHistoryError):
        preflight(context[0], request(**changes), now_ms=101000)


def test_exact_stop_distance_and_quote_age_boundary(context):
    result = preflight(context[0], request(stop=2999.5), now_ms=105000)
    assert result['status'] == 'read_only_preflight_passed'


def test_provider_exception_is_sanitized(context):
    def broken(_):
        raise RuntimeError('password=secret account=123456')
    context[0]._module.symbol_info_tick = broken
    with pytest.raises(BrokerHistoryError) as error:
        preflight(context[0], request(), now_ms=101000)
    assert 'secret' not in str(error.value) and '123456' not in str(error.value)


def test_identity_change_during_calculation(context):
    adapter = context[0]
    def changed(*args):
        adapter.account_key = 'b'*64
        return 100
    adapter._module.order_calc_margin = changed
    with pytest.raises(BrokerHistoryError):
        preflight(adapter, request(), now_ms=101000)
