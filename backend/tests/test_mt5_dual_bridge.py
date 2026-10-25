import json
from types import SimpleNamespace as NS
import pytest
from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_bridge_server import Bridge
from app.brokers.mt5_bridge_protocol import ProtocolError
from app.brokers.profiles import profiles
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from tests.test_mt5_import import Terminal
from tests.test_mt5_bridge import bridge,record


def runtime(environment):
    module=Terminal();module.terminal_info=lambda:NS(connected=True)
    module.account.trade_mode=0 if environment=='demo' else 2
    return module,Bridge(module,dict(environment=environment,expected_login=777,expected_server='fixture-server',
                                    terminal_path='fixture.exe',allow_initialize=True))


@pytest.mark.parametrize('environment',['demo','live'])
def test_environment_identity_and_readonly_operations(environment):
    module,bridge=runtime(environment)
    request={'method':'open','environment':environment}
    opened=bridge.dispatch(request)
    assert opened['environment']==environment
    auth={'lease':opened['lease'],'environment':environment}
    assert bridge.dispatch(dict(auth,method='account_info'))['record']['trade_mode']==module.account.trade_mode
    for method in ['order_send','order_check','login','shutdown']:
        with pytest.raises(ProtocolError):bridge.dispatch(dict(auth,method=method))
    module.account.server='different'
    with pytest.raises(ProtocolError,match='identity_mismatch'):bridge.dispatch(dict(auth,method='account_info'))


def test_live_requires_explicit_live_protocol_and_demo_remains_legacy_compatible():
    _,live=runtime('live');_,demo=runtime('demo')
    with pytest.raises(ProtocolError,match='identity_mismatch'):live.dispatch({'method':'open'})
    assert demo.dispatch({'method':'open'})['environment']=='demo'
    live.module.account.trade_mode=0
    with pytest.raises(ProtocolError,match='identity_mismatch'):live.dispatch({'method':'open','environment':'live'})


def test_private_profile_overlay_preserves_profiles_and_pins_saved_environment(tmp_path):
    overlay=tmp_path/'profiles.json'
    overlay.write_text(json.dumps([dict(id='mt5-live',provider='mt5',environment='live',credentials={
        'bridge_url':'http://127.0.0.1:18766','bridge_token_file':'private-live-token'})]))
    settings=Settings(_env_file=None,BROKER_PROFILES_JSON='[]',BROKER_PROFILES_FILE=str(overlay),
                      MT5_ENVIRONMENT='demo',MT5_BRIDGE_URL='http://127.0.0.1:18765')
    db=Database(tmp_path/'isolated.db');db.initialize()
    db.set_setting('broker_connection:mt5-default',json.dumps({'environment':'live'}))
    db.set_setting('broker_connection:mt5-live',json.dumps({'environment':'demo'}))
    connections=BrokerConnections(settings,db)
    assert connections.profiles['mt5-default'].environment=='demo'
    assert connections.profiles['mt5-live'].environment=='live'
    with pytest.raises(BrokerHistoryError,match='pinned'):connections.configure_connection('mt5-live',True,'demo')
    assert len(profiles(settings))==len(profiles(settings))
    overlay.write_text(json.dumps([dict(id='mt5-default',provider='mt5',environment='live')]))
    with pytest.raises(BrokerHistoryError):profiles(settings)


def test_two_real_http_bridges_reconcile_same_tickets_without_collisions(bridge,tmp_path):
    from threading import Thread
    from app.brokers.mt5_bridge_server import make_server
    from app.brokers.mt5_bridge_client import BridgeClient
    from app.brokers.metatrader5 import MetaTrader5History
    from app.storage.journal_repository import JournalRepository
    native,live=runtime('live')
    for method in ('history_deals_get','symbol_info'):
        original=getattr(native,method)
        setattr(native,method,lambda *a,_fn=original,**kw:record(_fn(*a,**kw)))
    token=tmp_path/'live-token';token.write_text('l'*64)
    server=make_server(live,'l'*64,0);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url=f'http://127.0.0.1:{server.server_port}'
        assert url!=bridge[2]
        with pytest.raises(BrokerHistoryError,match='unauthorized'):
            BridgeClient(url,str(bridge[3]),'live').initialize()
        extra=[dict(id='mt5-live',provider='mt5',environment='live',credentials={'bridge_url':url,'bridge_token_file':str(token)})]
        settings=Settings(_env_file=None,MT5_ENABLED=True,MT5_ENVIRONMENT='demo',MT5_BRIDGE_URL=bridge[2],MT5_BRIDGE_TOKEN_FILE=str(bridge[3]),BROKER_PROFILES_JSON=json.dumps(extra),BROKER_PROFILES_FILE='')
        db=Database(tmp_path/'dual.db');db.initialize()
        connections=BrokerConnections(settings,db,factories={'mt5':lambda c,e:MetaTrader5History(c,e,clock=lambda:native.now)})
        assert connections.sync('mt5-default')['created']==1
        assert connections.sync('mt5-live')['created']==1
        rows=JournalRepository(db).list_trades();assert len(rows)==2 and rows[0]['id']!=rows[1]['id']
        assert connections.sync('mt5-default')['created']==0
        assert connections.sync('mt5-live')['created']==0
        native.fail=True
        with pytest.raises(BrokerHistoryError):connections.sync('mt5-live')
        assert {row['id'] for row in JournalRepository(db).list_trades()}=={row['id'] for row in rows}
        assert connections.sync('mt5-default')['created']==0
    finally:
        server.shutdown();server.server_close();thread.join(2)
