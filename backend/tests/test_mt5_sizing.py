from types import SimpleNamespace as NS

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.brokers import router
from app.api.dependencies import get_services
from app.brokers.base import BrokerHistoryError
from tests.test_mt5_symbol_catalog import setup


@pytest.fixture
def sizing(setup):
    service, terminal, db = setup
    original = terminal.account_info
    terminal.account_info = lambda: NS(**vars(original()), balance=10000, equity=9000, margin_free=3000)
    terminal.ORDER_TYPE_BUY, terminal.ORDER_TYPE_SELL = 0, 1
    terminal.symbol_info = lambda s: NS(name=s, volume_min=.01, volume_max=50., volume_step=.01, trade_tick_size=.01)
    terminal.order_calc_profit = lambda side, symbol, lots, entry, stop: (stop-entry)*(1 if side==0 else -1)*lots*100
    terminal.order_calc_margin = lambda side, symbol, lots, entry: lots*1000
    def forbidden(*a, **kw):raise AssertionError('Order operations are forbidden')
    terminal.order_send = terminal.order_check = forbidden
    return service, terminal, db


def request(**kw):
    return dict(symbol='XAUUSDs', side='buy', entry=3000, stop=2991, risk_amount=100, **kw)


@pytest.mark.parametrize('side,stop',[('buy',2991),('sell',3009)])
def test_account_currency_lots_round_down_and_actual_risk(sizing,side,stop):
    service,terminal,_=sizing
    result=service.sizing_preview('mt5-default',{**request(),'side':side,'stop':stop})
    assert result['quantity_lots']==.11 and result['actual_estimated_risk']==99
    assert result['estimated_margin']==110 and result['currency']=='USD'
    assert result['execution_enabled'] is False and result['rejection_reason'] is None
    assert 'login' not in result and 'server' not in result
    assert terminal.calls[-1]=='shutdown'


def test_percent_uses_current_equity_not_balance(sizing):
    service,_,_=sizing
    body=request();del body['risk_amount'];body['risk_percent']=1
    result=service.sizing_preview('mt5-default',body)
    assert result['target_risk']==90 and result['quantity_lots']==.1


@pytest.mark.parametrize('change,reason',[
    ({'risk_amount':1},'minimum_lot_exceeds_target_risk'),
    ({'risk_amount':4000},'insufficient_free_margin'),
])
def test_unaffordable_sizes_are_explicit(sizing,change,reason):
    service,_,_=sizing
    result=service.sizing_preview('mt5-default',{**request(),**change})
    assert result['rejection_reason']==reason
    assert result['execution_enabled'] is False


@pytest.mark.parametrize('field,value',[('stop',3001),('entry',float('nan')),('risk_percent',1),('risk_amount',-1),('side','other')])
def test_invalid_input_never_connects(sizing,field,value):
    service,terminal,_=sizing;before=list(terminal.calls)
    with pytest.raises(BrokerHistoryError):service.sizing_preview('mt5-default',{**request(),field:value})
    assert terminal.calls==before


@pytest.mark.parametrize('failure',['none','secret','account','positive','nonlinear'])
def test_provider_failure_is_safe_and_lock_released(sizing,failure):
    service,terminal,_=sizing
    original=terminal.order_calc_profit
    def bad(*args):
        if failure=='secret':raise RuntimeError('password=secret')
        if failure=='none':return None
        if failure=='account':terminal.login=456
        if failure=='positive':return 100
        if failure=='nonlinear':return original(*args)*(2 if args[2]>.01 else 1)
        return original(*args)
    terminal.order_calc_profit=bad
    if failure=='nonlinear':
        result=service.sizing_preview('mt5-default',request())
        assert result['rejection_reason']=='rounded_size_exceeds_target_risk'
    else:
        with pytest.raises(BrokerHistoryError) as error:service.sizing_preview('mt5-default',request())
        assert 'secret' not in str(error.value)
    assert terminal.calls[-1]=='shutdown'
    terminal.login=123;terminal.order_calc_profit=original
    assert service.sizing_preview('mt5-default',request())['quantity_lots']==.11


def test_api_and_disabled_profile(sizing):
    service,terminal,_=sizing
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:NS(broker_connections=service)
    with TestClient(app) as client:
        path='/brokers/mt5-default/sizing-preview'
        assert client.post(path,json=request()).json()['execution_enabled'] is False
        assert client.post(path,json={**request(),'submit':True}).status_code==422
        assert client.post(path,json={**request(),'entry':3000.001}).status_code==400
        service.configure_connection('mt5-default',False,'demo');before=list(terminal.calls)
        assert client.post(path,json=request()).status_code==400
        assert terminal.calls==before


def test_maximum_lots_and_account_change_before_calculation(sizing):
    service,terminal,_=sizing
    result=service.sizing_preview('mt5-default',{**request(),'risk_amount':100000})
    assert result['quantity_lots']==50 and result['sizing_limited']
    terminal.login=456
    with pytest.raises(BrokerHistoryError,match='no longer connected'):
        service.sizing_preview('mt5-default',request())
    assert terminal.calls[-1]=='shutdown'


def test_missing_symbol_and_invalid_margin_fail_closed(sizing):
    service,terminal,_=sizing
    symbol=terminal.symbol_info
    terminal.symbol_info=lambda s:None
    with pytest.raises(BrokerHistoryError,match='Unknown'):service.sizing_preview('mt5-default',request())
    terminal.symbol_info=symbol
    terminal.order_calc_margin=lambda *a:float('nan')
    with pytest.raises(BrokerHistoryError):service.sizing_preview('mt5-default',request())


def test_live_estimate_cannot_enable_execution(sizing):
    service,terminal,_=sizing
    service.configure_connection('mt5-default',True,'live');terminal.mode=2
    key=service.discover('mt5-default')['items'][0]['account_key']
    service.select_account('mt5-default',key)
    result=service.sizing_preview('mt5-default',request())
    assert result['environment']=='live' and result['execution_enabled'] is False
