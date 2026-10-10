from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import pytest
from app.backtesting.strategies import strategy_registry
from app.research_agent.repository import ResearchRepository
from app.research_agent.hypotheses import HypothesisRepository, Hypothesis
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


@pytest.fixture
def registered(tmp_path):
    db=Database(tmp_path/'hypotheses.db');db.initialize();repo=ResearchRepository(db)
    spec=next(s for s in strategy_registry.specs() if any(p.kind=='int' for p in s.parameters))
    param=next(p for p in spec.parameters if p.kind=='int')
    project=repo.create('Bounded',spec.key,[dict(symbols=['QQQ'],timeframe='1m',start='2024-01-01',end='2024-12-31',state='DEVELOPMENT'),dict(symbols=['QQQ'],timeframe='1m',start='2025-01-01',end='2025-12-31',state='LOCKED_HOLDOUT')],{'max_hypotheses':2,'max_total_variants':2,'max_variants_per_hypothesis':1})
    base=dict(strategy_key=spec.key,symbols=['QQQ'],primary_timeframe='1m',start_date='2024-02-01',end_date='2024-02-02',strategy_params=dict(spec.defaults),market_data_fingerprint='fixture')
    saved=BacktestRunRepository(db).create(config=base,result={'trades':[],'metrics':{},'strategy':{'implementation':strategy_registry.provenance(spec.key)}})
    repo.inspect_run(project['id'],saved['id'])
    proposal=dict(request_key='one',description='Test declared parameter',rationale='Economic mechanism',feature=param.key,
        discovery_dataset_ids=[project['datasets'][0]['id']],expected_result='Broad improvement in each development year',falsification='Only one period benefits',researcher_reasoning='Recorded user reasoning',devils_advocate_objections='Small sample; protect large winners',axes=[{'parameter':param.key,'values':[param.default]}])
    return db,repo,project,proposal


def test_immutable_preregistration_idempotency_and_atomic_budget(registered):
    db,repo,project,proposal=registered;store=HypothesisRepository(db)
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:store.register(project['id'],proposal),range(4)))
    assert len({r['id'] for r in results})==1
    assert results[0]['status']=='PREREGISTERED' and not results[0]['execution_enabled']
    assert results[0]['plan']['job_count']==1 and results[0]['base_config_hash']
    with pytest.raises(ValueError,match='different'):store.register(project['id'],{**proposal,'description':'Changed after registration'})
    store.register(project['id'],{**proposal,'request_key':'two'})
    with pytest.raises(ValueError,match='budget'):store.register(project['id'],{**proposal,'request_key':'three'})
    assert len(HypothesisRepository(db).list(project['id']))==2
    assert len([e for e in repo.get(project['id'])['events'] if e['action']=='hypothesis_preregistered'])==2
    assert len(BacktestRunRepository(db).list())==1


def test_locked_discovery_and_arbitrary_axes_rejected_without_writes(registered):
    db,_,project,proposal=registered;store=HypothesisRepository(db)
    with pytest.raises(ValueError,match='locked holdout'):store.register(project['id'],{**proposal,'discovery_dataset_ids':[project['datasets'][1]['id']]})
    with pytest.raises(ValueError):store.register(project['id'],{**proposal,'axes':[{'parameter':'arbitrary_code','values':[1]}]})
    with pytest.raises(ValueError):Hypothesis.model_validate({**proposal,'shell':'execute'})
    with pytest.raises(ValueError):Hypothesis.model_validate({**proposal,'axes':[{'parameter':'test','values':[True]}]})
    assert not store.list(project['id'])


def test_paused_project_cannot_preregister(registered):
    db,repo,project,proposal=registered;repo.transition(project['id'],'PAUSED')
    with pytest.raises(ValueError,match='active project'):HypothesisRepository(db).register(project['id'],proposal)


def test_api_returns_registered_record_and_preserves_budget(registered):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    db,_,project,proposal=registered
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        path='/api/strategy-lab/research-agent/'+project['id']+'/hypotheses'
        response=client.post(path,json=proposal)
        assert response.status_code==200,response.text
        assert client.get(path).json()['items']==[response.json()]
        assert client.post(path,json={**proposal,'execute':True}).status_code==422


def test_changed_source_blocks_preregistration(registered,monkeypatch):
    db,_,project,proposal=registered
    monkeypatch.setattr(strategy_registry,'provenance',lambda key:{'changed':True})
    store=HypothesisRepository(db)
    with pytest.raises(ValueError,match='source changed'):store.register(project['id'],proposal)
    assert store.list(project['id'])==[]
