from collections import namedtuple
from datetime import datetime, timezone
import http.client
import json
from threading import Thread
from types import SimpleNamespace as NS
import numpy as np
import pytest
from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_bridge_client import BridgeClient,decode
from app.brokers.mt5_bridge_protocol import ProtocolError,encode,validate
from app.brokers.mt5_bridge_server import Bridge,make_server
from app.brokers.metatrader5 import MetaTrader5History
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from tests.test_mt5_import import Terminal,deal


def record(value):
    if isinstance(value,NS):return namedtuple('Record',vars(value))(**vars(value))
    if isinstance(value,list):return [record(v) for v in value]
    return value


@pytest.fixture
def bridge(tmp_path):
    native=Terminal();native.ACCOUNT_TRADE_MODE_DEMO=0
    native.terminal_info=lambda:NS(connected=True,trade_allowed=True)
    native.symbol_info_tick=lambda symbol:NS(time_msc=1792719348844,bid=4000.,ask=4001.)
    for method in ('history_deals_get','symbol_info','symbol_info_tick'):
        original=getattr(native,method)
        setattr(native,method,lambda *a,_fn=original,**k:record(_fn(*a,**k)))
    config=dict(environment='demo',allow_initialize=True,expected_login=777,expected_server='fixture-server',terminal_path='fixture.exe')
    runtime=Bridge(native,config)
    token=tmp_path/'token';token.write_text('x'*64)
    server=make_server(runtime,'x'*64,0);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    yield native,runtime,url,token,server
    server.shutdown();server.server_close();thread.join(2)


def client(bridge):return BridgeClient(bridge[2],str(bridge[3]),'demo')


def test_wire_records_arrays_and_utc_arguments():
    row=namedtuple('Tick','time_msc bid')(1792719348844,12.5)
    assert decode(encode(row)).time_msc==1792719348844
    array=np.array([(123,10.)],dtype=[('time','i8'),('close','f8')])
    assert decode(encode(array))==[{'time':123,'close':10.}]
    args,_=validate('history_deals_get',[0,100],{})
    assert args[0].tzinfo==timezone.utc


@pytest.mark.parametrize('method,args,kwargs',[
    ('order_send',[{}],{}),('login',[123],{}),('__import__',['os'],{}),
    ('symbol_select',['XAUUSDs',False],{}),('positions_get',[],{'ticket':1}),
    ('history_deals_get',[],{'position':True}),('copy_ticks_range',['X',0,90000,'COPY_TICKS_ALL'],{})])
def test_readonly_allowlist(method,args,kwargs):
    with pytest.raises(ProtocolError):validate(method,args,kwargs)


def test_session_identity_no_credentials_no_execution(bridge):
    native,runtime,_,_,_=bridge
    c=client(bridge);assert c.initialize(timeout=30000)
    assert c.account_info().trade_mode==0
    with pytest.raises(AttributeError):c.order_send({})
    other=client(bridge)
    with pytest.raises(BrokerHistoryError,match='busy'):other.initialize()
    native.account.login=778
    with pytest.raises(BrokerHistoryError,match='identity_mismatch'):c.account_info()
    c.shutdown()
    assert native.calls[0]==('initialize',('fixture.exe',),{'timeout':30000})


def test_raw_tick_diagnostics_do_not_invent_utc_or_seasonal_conversion(bridge):
    c=client(bridge);c.initialize()
    diagnostics=c.tick_diagnostics('XAUUSDs')
    assert diagnostics['raw_time_msc']==1792719348844
    assert diagnostics['timestamp_policy']=='unverified' and not diagnostics['seasonal_rule_verified']
    with pytest.raises(BrokerHistoryError,match='timestamp_unverified'):
        c._call('copy_rates_range',['X','TIMEFRAME_M1',0,60])
    c.shutdown()


def test_disconnect_expiry_and_live_profile_rejected(bridge):
    with pytest.raises(BrokerHistoryError,match='DEMO'):BridgeClient(bridge[2],str(bridge[3]),'live')
    c=client(bridge);c.initialize();bridge[0].terminal_info=lambda:NS(connected=False)
    with pytest.raises(BrokerHistoryError,match='disconnected'):c.account_info()
    bridge[1].expires=0
    with pytest.raises(BrokerHistoryError,match='session_expired'):c.account_info()


@pytest.mark.parametrize('url',['http://localhost:18765','http://192.168.1.2:18765','https://127.0.0.1:18765','http://127.0.0.1:18765/path'])
def test_non_loopback_or_ambiguous_url_rejected(url):
    with pytest.raises(BrokerHistoryError):BridgeClient(url,'unused','demo')


def test_http_auth_origin_and_unsupported_method(bridge):
    server=bridge[4];assert server.server_address[0]=='127.0.0.1'
    for headers,body in [({},{}),({'Authorization':'Bearer '+'x'*64,'Origin':'http://evil'},{}),
                        ({'Authorization':'Bearer '+'x'*64},{'method':'order_send'})]:
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        connection.request('POST','/v1/read',json.dumps(body),{'Content-Type':'application/json',**headers})
        response=connection.getresponse();assert response.status in (400,401);response.read();connection.close()


def test_unavailable_bridge_does_not_import_windows_package_or_break_startup(tmp_path,monkeypatch):
    monkeypatch.setattr('app.brokers.metatrader5.importlib.import_module',lambda name:pytest.fail('Native import'))
    c=MetaTrader5History({'bridge_url':'http://127.0.0.1:1','bridge_token_file':str(tmp_path/'missing')},'demo')
    with pytest.raises(BrokerHistoryError):c.connect()
    assert not c._locked


def test_real_http_adapter_journal_idempotency_partial_and_failure_cursor(bridge,tmp_path):
    native,_,url,token,_=bridge
    db=Database(tmp_path/'ledger.db');db.initialize()
    settings=Settings(_env_file=None,MT5_ENABLED=True,MT5_ENVIRONMENT='demo',MT5_BRIDGE_URL=url,MT5_BRIDGE_TOKEN_FILE=str(token))
    connections=BrokerConnections(settings,db,factories={'mt5':lambda credentials,environment:MetaTrader5History(credentials,environment,clock=lambda:native.now)})
    discovered=connections.discover('mt5-default')
    assert discovered['items'][0]['environment']=='demo'
    first=connections.sync('mt5-default');assert first['created']==1
    before=JournalRepository(db).list_trades();assert len(before)==1
    assert connections.sync('mt5-default')['executions_changed']==0
    native.deals += [deal(3,0,0,2,100,position=20),deal(4,1,1,1,110,10,position=20)]
    connections.sync('mt5-default');assert len(JournalRepository(db).list_trades())==1
    native.deals.append(deal(5,1,1,1,111,11,position=20))
    assert connections.sync('mt5-default')['created']==1
    assert connections.sync('mt5-default')['executions_changed']==0
    key=discovered['items'][0]['account_key']
    cursor=connections.state.state('mt5',key)['cursor']
    native.fail=True
    with pytest.raises(BrokerHistoryError):connections.sync('mt5-default')
    assert connections.state.state('mt5',key)['cursor']==cursor
    assert len(JournalRepository(db).list_trades())==2
    assert before[0]['id'] in {r['id'] for r in JournalRepository(db).list_trades()}


@pytest.mark.parametrize('field,value',[('trade_mode',2),('server','another-server'),('login',123)])
def test_initial_native_identity_mismatch_never_opens_lease(bridge,field,value):
    setattr(bridge[0].account,field,value)
    with pytest.raises(BrokerHistoryError,match='identity_mismatch'):client(bridge).initialize()
    assert bridge[1].lease is None


def test_timeout_redacts_native_errors_and_does_not_retry(bridge,monkeypatch):
    calls=[]
    class Connection:
        def __init__(self,*a,**kw):assert kw['timeout']==40
        def request(self,*a,**kw):calls.append(1);raise TimeoutError('PRIVATE_ACCOUNT_SECRET')
        def close(self):pass
    monkeypatch.setattr('app.brokers.mt5_bridge_client.http.client.HTTPConnection',Connection)
    with pytest.raises(BrokerHistoryError) as exc:client(bridge).initialize()
    assert len(calls)==1 and 'PRIVATE_ACCOUNT_SECRET' not in str(exc.value)


def test_http_rejects_oversized_request_before_dispatch(bridge):
    connection=http.client.HTTPConnection('127.0.0.1',bridge[4].server_port,timeout=2)
    connection.request('POST','/v1/read','x'*17000,{'Content-Type':'application/json','Authorization':'Bearer '+'x'*64})
    response=connection.getresponse();assert response.status==400
    assert json.loads(response.read())=={'error':'request_limit'}
    connection.close();assert bridge[0].calls==[]


def test_verified_utc_history_roundtrip_uses_native_constants_and_utc(bridge):
    native,runtime,_,_,_=bridge
    runtime.config['timestamp_policy']='verified_utc';native.TIMEFRAME_M1=1
    calls=[]
    def rates(symbol,frame,start,end):
        calls.append((symbol,frame,start,end))
        return np.array([(60,10.,11.,9.,10.,4,0,2)],dtype=[('time','i8'),('open','f8'),('high','f8'),('low','f8'),('close','f8'),('tick_volume','i8'),('real_volume','i8'),('spread','i8')])
    native.copy_rates_range=rates
    c=client(bridge);c.initialize()
    rows=c.copy_rates_range('XAUUSDs',c.TIMEFRAME_M1,datetime.fromtimestamp(0,timezone.utc),datetime.fromtimestamp(120,timezone.utc))
    assert rows[0]['time']==60 and calls[0][1]==1 and calls[0][2].tzinfo==timezone.utc
    c.shutdown()
