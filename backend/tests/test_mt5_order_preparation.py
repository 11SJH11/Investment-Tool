from types import SimpleNamespace as NS

import pytest

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_order_preparation import prepare
from tests.test_mt5_execution_preflight import context, request


@pytest.fixture
def prepared(context):
    adapter, account, terminal, symbol, quote = context
    adapter._clock = lambda: 101.
    constants = dict(SYMBOL_FILLING_FOK=1, SYMBOL_FILLING_IOC=2, ORDER_FILLING_FOK=0,
                     ORDER_FILLING_IOC=1, SYMBOL_TRADE_EXECUTION_REQUEST=0,
                     SYMBOL_TRADE_EXECUTION_INSTANT=1, SYMBOL_TRADE_EXECUTION_MARKET=2,
                     SYMBOL_TRADE_EXECUTION_EXCHANGE=3, TRADE_ACTION_DEAL=1, ORDER_TIME_GTC=0)
    for key, value in constants.items():
        setattr(adapter._module, key, value)
    symbol.filling_mode, symbol.trade_exemode = 3, 2
    checks = []
    def check(body):
        checks.append(body)
        return NS(retcode=0, margin_free=1000., comment='private-native-text')
    adapter._module.order_check = check
    return context, checks


def run(prepared, **changes):
    return prepare(prepared[0][0], request(),
                   **(dict(intent_id='intent-1', magic=12345, deviation_points=10) | changes))


def test_protected_market_request_checked_but_never_submitted(prepared):
    # Match actual Python package: symbol bitmask enums are not exported.
    for name in ('SYMBOL_ORDER_MARKET', 'SYMBOL_ORDER_SL', 'SYMBOL_ORDER_TP',
                 'SYMBOL_FILLING_FOK', 'SYMBOL_FILLING_IOC'):
        delattr(prepared[0][0]._module, name)
    result = run(prepared)
    assert result['status'] == 'broker_check_passed'
    assert result['request']['sl'] == 2991 and result['request']['tp'] == 3011
    assert result['request']['volume'] == .1
    assert 'price' not in result['request']
    assert result['request']['type_filling'] == 0
    assert not result['execution_enabled'] and not result['orders_sent']
    assert len(prepared[1]) == 1 and 'private-native-text' not in str(result)
    assert run(prepared)['request']['comment'] == result['request']['comment']


def test_ioc_and_instant_price_use_broker_metadata(prepared):
    symbol = prepared[0][3]
    symbol.filling_mode, symbol.trade_exemode = 2, 1
    result = run(prepared)
    assert result['request']['type_filling'] == 1
    assert result['request']['price'] == 3001


@pytest.mark.parametrize('field,value', [('filling_mode', 0), ('trade_exemode', 99)])
def test_unsupported_modes_do_not_call_broker_check(prepared, field, value):
    setattr(prepared[0][3], field, value)
    with pytest.raises(BrokerHistoryError): run(prepared)
    assert not prepared[1]


@pytest.mark.parametrize('changes', [{'magic': True}, {'magic': 0}, {'deviation_points': -1},
                                    {'deviation_points': 1.5}, {'intent_id': ''}])
def test_invalid_identity_and_execution_inputs(prepared, changes):
    with pytest.raises(BrokerHistoryError): run(prepared, **changes)
    assert not prepared[1]


def test_live_account_rejected_before_broker_check(prepared):
    prepared[0][1].trade_mode = 2
    with pytest.raises(BrokerHistoryError): run(prepared)
    assert not prepared[1]


def test_broker_rejection_is_not_an_accepted_order(prepared):
    prepared[0][0]._module.order_check = lambda _: NS(retcode=10019, comment='private')
    result = run(prepared)
    assert result['status'] == 'broker_check_rejected' and result['broker_retcode'] == 10019
    assert not result['orders_sent'] and 'private' not in str(result)


@pytest.mark.parametrize('failure', ['none', 'exception', 'account', 'expired', 'margin'])
def test_failed_changed_or_expired_check_fails_closed(prepared, failure):
    adapter = prepared[0][0]
    def check(_):
        if failure == 'none': return None
        if failure == 'exception': raise RuntimeError('password-secret')
        if failure == 'account': adapter.account_key = 'b'*64
        if failure == 'expired': adapter._clock = lambda: 110.
        return NS(retcode=0, margin_free=-1. if failure == 'margin' else 1000.)
    adapter._module.order_check = check
    with pytest.raises(BrokerHistoryError) as error: run(prepared)
    assert 'password-secret' not in str(error.value)
