from types import SimpleNamespace as NS
import json
import pytest
from app.brokers.base import BrokerHistoryError
from tests.test_mt5_symbol_catalog import setup


@pytest.fixture
def account(setup):
    service,terminal,db=setup
    original=terminal.account_info
    terminal.account_info=lambda:NS(**vars(original()),balance=10000,equity=9990,margin=100,margin_free=9890,password='secret')
    terminal.positions_get=lambda:()
    terminal.orders_get=lambda:()
    return service,terminal,db


def test_snapshot_allowlist_no_credentials_or_implicit_execution(account):
    service,terminal,_=account
    result=service.account_snapshot('mt5-default')
    assert result['account']==dict(balance=10000,equity=9990,margin=100,margin_free=9890,currency='USD')
    assert result['positions']==result['pending_orders']==[]
    assert result['execution_enabled'] is False and result['snapshot_atomic'] is False
    assert 'secret' not in json.dumps(result) and 'login' not in json.dumps(result)
    assert terminal.calls[-1]=='shutdown'


@pytest.mark.parametrize('failure',['positions','orders','changed','exception','invalid'])
def test_incomplete_snapshot_never_means_empty_holdings(account,failure):
    service,terminal,_=account
    if failure=='positions':terminal.positions_get=lambda:None
    if failure=='orders':terminal.orders_get=lambda:None
    if failure=='changed':
        def changed():terminal.login=456;return ()
        terminal.orders_get=changed
    if failure=='exception':
        def bad():raise RuntimeError('secret')
        terminal.orders_get=bad
    if failure=='invalid':terminal.positions_get=lambda:[NS(ticket=1)]
    with pytest.raises(BrokerHistoryError) as error:service.account_snapshot('mt5-default')
    assert 'secret' not in str(error.value)
    assert terminal.calls[-1]=='shutdown'


def test_position_and_pending_order_facts_preserved(account):
    service,terminal,_=account
    p=dict(ticket=1,identifier=2,symbol='XAUUSDs',type=1,volume=.1,price_open=4200,price_current=4201,sl=4210,tp=4180,profit=-10,swap=-.1,time_msc=1000)
    o=dict(ticket=3,symbol='XAUUSDs',type=2,state=1,volume_initial=.1,volume_current=.05,price_open=4100,sl=4090,tp=4120,time_setup_msc=2000)
    terminal.positions_get=lambda:[NS(**p,comment='private')]
    terminal.orders_get=lambda:[NS(**o,comment='private')]
    result=service.account_snapshot('mt5-default')
    assert result['positions']==[p] and result['pending_orders']==[o]


def test_disabled_profile_does_not_connect(account):
    service,terminal,_=account
    service.configure_connection('mt5-default',False,'demo');before=list(terminal.calls)
    with pytest.raises(BrokerHistoryError):service.account_snapshot('mt5-default')
    assert terminal.calls==before
