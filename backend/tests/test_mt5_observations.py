import json
from types import SimpleNamespace
import pytest
from app.brokers.base import BrokerHistoryError
from app.services.algo_monitoring import report,account_totals
from app.storage import mt5_observations as observations
from tests.test_mt5_account import account
from tests.test_mt5_symbol_catalog import setup


def test_snapshot_survives_restart_failure_and_never_attributes_positions(account):
    service,terminal,db=account
    snapshot=service.account_snapshot('mt5-default')
    before=list(terminal.calls)
    result=report(SimpleNamespace(database=db,broker_connections=service))
    assert terminal.calls==before  # Polling reads SQLite, never the broker.
    assert result['items']==[] and result['broker_totals'][0]['equity']==9990
    assert not result['mt5_execution_enabled']
    terminal.positions_get=lambda:None
    with pytest.raises(BrokerHistoryError):service.account_snapshot('mt5-default')
    recovered=observations.read(db,snapshot['account_key'],'demo',history=True)
    assert recovered['snapshot']==snapshot
    assert recovered['error_category']=='snapshot_unavailable' and len(recovered['history'])==1
    assert observations.read(db,snapshot['account_key'],'live',history=True)['snapshot'] is None
    assert observations.read(db,'different','demo',history=True)['snapshot'] is None
    assert 'secret' not in json.dumps(result)


def test_snapshot_history_is_bounded_readonly_and_resets_error_after_success(account):
    service,terminal,db=account
    before=list(terminal.calls)
    assert service.account_observations('mt5-default')['snapshot'] is None
    assert terminal.calls==before
    snapshot=service.account_snapshot('mt5-default')
    observations.failed(db,snapshot['account_key'],'demo')
    for _ in range(1002):observations.save(db,snapshot)
    result=service.account_observations('mt5-default')
    assert len(result['history'])==1000 and result['error_category'] is None
    assert result['history'][0]['id']<result['history'][-1]['id']
    service.configure_connection('mt5-default',False,'demo')
    assert service.account_observations('mt5-default')['snapshot']==snapshot


def test_account_totals_deduplicate_identity_and_separate_currencies_environments():
    def row(key,env,currency,balance,time='2026-10-25T12:00:00+00:00'):
        return dict(account_key=key,environment=env,observation=dict(observed_at=time,facts=dict(currency=currency,balance=balance,equity=balance+1)))
    rows=[row('a','demo','USD',10),row('a','demo','USD',20,'2026-10-25T13:00:00+00:00'),row('b','demo','USD',30),row('c','demo','EUR',40),row('d','live','USD',50)]
    totals={(r['environment'],r['currency']):r for r in account_totals(rows)}
    assert len(totals)==3
    assert totals['demo','USD']['accounts']==2 and totals['demo','USD']['balance']==50
    assert totals['demo','EUR']['balance']==40 and totals['live','USD']['balance']==50


def test_observation_endpoint_reads_no_native_calls(account):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.brokers import router
    service,terminal,db=account
    snapshot=service.account_snapshot('mt5-default');before=list(terminal.calls)
    app=FastAPI();app.include_router(router)
    app.state.services=SimpleNamespace(broker_connections=service)
    with TestClient(app) as client:
        response=client.get('/brokers/mt5-default/account-observations')
        assert response.status_code==200 and response.json()['snapshot']==snapshot
    assert terminal.calls==before


def test_monitor_does_not_label_new_account_facts_as_previous_selection(account):
    service,terminal,db=account
    snapshot=service.account_snapshot('mt5-default')
    snapshot['account_key']='other-account'
    service.account_observations=lambda *a,**kw:dict(snapshot=snapshot,last_attempt_at=None,error_category=None)
    result=report(SimpleNamespace(database=db,broker_connections=service))
    assert result['accounts'][0]['observation']['facts'] is None
    assert result['broker_totals'] is None
