from copy import deepcopy
from types import SimpleNamespace as NS
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.algo_trading import router
from app.backtesting.strategies import strategy_registry
from app.forward.mt5_t01_runtime import T02_KEY
from app.services.mt5_deployments import MT5Deployments
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


@pytest.fixture
def prepared(tmp_path):
    db=Database(tmp_path/'drafts.db');db.initialize()
    runs=BacktestRunRepository(db)
    run=runs.create(config=dict(strategy_key=T02_KEY,symbols=['XAUUSD'],primary_timeframe='1m',strategy_params={'direction':'both'}),
        result={'strategy':{'key':T02_KEY,'implementation':strategy_registry.provenance(T02_KEY)},'primary_timeframe':'1m'},strategy_sources=strategy_registry.sources())
    account_key='a'*64
    status=dict(provider='mt5',environment='demo',configured=True,account_key=account_key)
    snapshot=dict(environment='demo',account_key=account_key,observed_at='2026-10-25T12:00:00Z',account=dict(currency='USD',equity=10000))
    connections=NS(status=lambda _:status,symbol_catalog=lambda *a,**kw:dict(items=[dict(name='XAUUSDs',account_key=account_key,environment='demo',currency_base='XAU',currency_profit='USD')]),account_observations=lambda *a,**kw:dict(snapshot=snapshot))
    request=dict(request_key='one',name='T02 demo',run_id=run['id'],profile_id='mt5-default',broker_symbol='XAUUSDs',max_gross_exposure=10000)
    return MT5Deployments(db,connections),request,runs,status


def test_immutable_saved_run_draft_is_unarmed_and_idempotent(prepared):
    repo,request,runs,_=prepared;before=runs.get(request['run_id'])
    preview=repo.preview(request)
    assert repo.list()==[] and preview['estimated_target_risk']==50
    first=repo.create(request)
    assert first==repo.create(request) and len(repo.list())==1
    assert first['state']=='DRAFT' and not first['execution_enabled']
    assert first['definition']['parameters']=={'direction':'both'}
    assert first['definition']['saved_config']==before['config']
    assert first['definition']['session_timezone']=='America/New_York'
    assert runs.get(request['run_id'])==before
    with pytest.raises(ValueError,match='different deployment'):repo.create(request|dict(risk_percent=1))


def test_live_missing_identity_and_unknown_broker_symbol_rejected(prepared):
    repo,request,_,status=prepared
    status['environment']='live'
    with pytest.raises(ValueError,match='DEMO'):repo.create(request)
    status['environment']='demo'
    with pytest.raises(ValueError,match='exact XAU'):repo.create(request|dict(broker_symbol='GUESS'))
    status['account_key']=None
    with pytest.raises(ValueError,match='DEMO'):repo.create(request)
    assert not repo.list()


def test_changed_implementation_or_archive_blocks_new_deployment(prepared,monkeypatch):
    repo,request,runs,_=prepared
    original=repo.registry.provenance
    monkeypatch.setattr(repo.registry,'provenance',lambda key:original(key)|{'source_sha256':'b'*64})
    with pytest.raises(ValueError,match='differs'):repo.preview(request)
    monkeypatch.setattr(repo.registry,'provenance',original)
    with repo.database.connect() as c:c.execute('DELETE FROM strategy_source_blobs')
    with pytest.raises(ValueError,match='integrity'):repo.preview(request)


def test_operator_authentication_origin_and_no_activation_route(prepared):
    repo,request,_,_=prepared;token='private-operator-fixture-'*3
    app=FastAPI();app.include_router(router)
    app.state.services=NS(database=repo.database,broker_connections=repo.connections,settings=NS(mt5_algo_control_token=token))
    with TestClient(app,base_url='https://ledger.test') as client:
        assert client.get('/algo-trading/deployments').status_code==401
        headers={'Authorization':'Bearer '+token}
        assert client.post('/algo-trading/deployments',json=request,headers={**headers,'Origin':'https://attacker.test'}).status_code==403
        response=client.post('/algo-trading/deployments',json=request,headers=headers)
        assert response.status_code==200 and token not in response.text
        assert response.headers['cache-control']=='no-store'
        assert client.post('/algo-trading/deployments/activate',headers=headers).status_code==404
    with TestClient(app,base_url='http://remote.test') as client:
        assert client.get('/algo-trading/deployments',headers=headers).status_code==403


def test_tampered_definition_is_never_returned_as_valid(prepared):
    repo,request,_,_=prepared
    item=repo.create(request)
    item['definition']['risk']['risk_percent']=5
    with repo.database.connect() as c:c.execute('UPDATE mt5_algo_deployments SET document=?',(json.dumps(item),))
    with pytest.raises(ValueError,match='integrity'):repo.list()
    with pytest.raises(ValueError,match='integrity'):repo.create(request)


def test_profile_change_during_preview_fails_closed(prepared):
    repo,request,_,status=prepared
    calls=[]
    def changing(_):
        calls.append(1)
        return {**status,'account_key':status['account_key'] if len(calls)==1 else 'b'*64}
    repo.connections.status=changing
    with pytest.raises(ValueError,match='changed during'):repo.preview(request)
    assert repo.list()==[]
