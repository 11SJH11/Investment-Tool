from dataclasses import replace
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.brokers import router
from app.api.dependencies import get_services
from app.brokers.base import BrokerHistoryError
from app.brokers.executions import Execution, closed_positions
from app.core.config import Settings
from app.services.broker_connections import BrokerConnections
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from tests.test_tradelocker_import import Provider, select
from tests.test_broker_connections import Provider as PortfolioProvider


def make(tmp_path):
    db=Database(tmp_path/'db');db.initialize();p=Provider()
    settings=Settings(_env_file=None,TRADELOCKER_ENABLED=True,TRADELOCKER_EMAIL='synthetic-email',
        TRADELOCKER_PASSWORD='synthetic-password',TRADELOCKER_SERVER='synthetic-server')
    s=BrokerConnections(settings,db,factories={'tradelocker':p.factory})
    return db,p,s,settings


def test_connection_api_accounts_configuration_disconnect_and_restart(tmp_path):
    db,p,s,settings=make(tmp_path)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(broker_connections=s)
    with TestClient(app) as client:
        assert client.get('/brokers').status_code==200 and not p.calls
        response=client.post('/brokers/tradelocker-default/test')
        assert response.status_code==200
        key=response.json()['items'][0]['account_key']
        assert client.put('/brokers/tradelocker-default/account',json={'account_key':key}).status_code==200
        assert client.post('/brokers/tradelocker-default/sync').json()['created']==1
        assert client.patch('/brokers/tradelocker-default/connection',json={'enabled':False,'environment':'demo'}).json()['status']=='disconnected'
        calls=len(p.calls)
        assert client.post('/brokers/tradelocker-default/sync').json()['status']=='disconnected'
        assert len(p.calls)==calls
        restarted=BrokerConnections(settings,db,factories={'tradelocker':p.factory})
        assert restarted.status('tradelocker-default')['disconnected']
        assert restarted.configure_connection('tradelocker-default',True,'demo')['configured']
        assert len(JournalRepository(db).list_trades())==1
        assert client.patch('/brokers/tradelocker-default/connection',json={'enabled':True,'environment':'bogus'}).status_code==422
        assert client.put('/brokers/tradelocker-default/account',json={'account_key':'raw-account-secret'}).status_code==422


def test_profile_operation_lock_blocks_reconfiguration(tmp_path):
    _,_,s,_=make(tmp_path)
    lock=s._profile_locks['tradelocker-default'];lock.acquire()
    try:
        for fn in (lambda:s.sync('tradelocker-default'),lambda:s.discover('tradelocker-default'),
                   lambda:s.configure_connection('tradelocker-default',False,'demo')):
            with pytest.raises(BrokerHistoryError,match='operation'):
                fn()
    finally:lock.release()


def test_pending_snapshot_imports_after_position_disappears_without_changed_orders(tmp_path):
    db,p,s,_=make(tmp_path);select(s);p.positions=[10]
    assert s.sync('tradelocker-default')['created']==0
    p.positions=[]
    result=s.sync('tradelocker-default')
    assert result['created']==1 and result['executions_changed']==0


def test_correction_cannot_leave_a_stale_closed_journal_trade(tmp_path):
    db,p,s,_=make(tmp_path);key=select(s);s.sync('tradelocker-default')
    before=JournalRepository(db).list_trades();cursor=s.state.state('tradelocker',key)['cursor']
    p.rows[-1]['filledQty']=.5
    with pytest.raises(BrokerHistoryError,match='invalidate'):
        s.sync('tradelocker-default')
    assert JournalRepository(db).list_trades()==before
    assert s.state.state('tradelocker',key)['cursor']==cursor


def test_trading212_canonical_fills_preserve_portfolio_destination(tmp_path):
    db=Database(tmp_path/'db');db.initialize();p=PortfolioProvider()
    s=BrokerConnections(Settings(_env_file=None,TRADING212_ENABLED=True,
        TRADING212_API_KEY='synthetic',TRADING212_API_SECRET='synthetic'),db,factories={'trading212':p.factory})
    s.sync('trading212-default');key=s.portfolio.accounts()[0]['account_key']
    rows=s.state.executions('trading212',key)
    assert len(rows)==2 and {r['external_id'] for r in rows}=={'9:1','9:2'}
    assert all(r['quantity_unit']=='shares' and r['position_id']=='' for r in rows)
    assert all(r['metadata']['destination']=='portfolio' for r in rows)
    s.sync('trading212-default');assert s.state.executions('trading212',key)==rows
    assert JournalRepository(db).list_trades()==[]
    p.failure='dividends'
    with pytest.raises(BrokerHistoryError):s.sync('trading212-default')
    assert s.state.executions('trading212',key)==rows


def test_canonical_timestamp_and_unknown_position_contract():
    e=Execution('fixture','demo','hash','1','2','','ABC','equity','buy','1','100',
                '2026-01-01T09:00:00-05:00','shares')
    assert e.timestamp=='2026-01-01T14:00:00+00:00'
    with pytest.raises(BrokerHistoryError,match='Position identity'):closed_positions([e],'Test','USD')
    with pytest.raises(BrokerHistoryError,match='timezone'):replace(e,timestamp='2026-01-01T09:00:00')
