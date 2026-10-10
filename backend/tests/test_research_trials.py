from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import json
import pandas as pd
import pytest
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.base import ParameterSpec
from app.services.backtest import BacktestService
from app.services.backtest_jobs import BacktestJobs
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.research_agent.repository import ResearchRepository
from app.research_agent.hypotheses import HypothesisRepository
from app.research_agent.trials import Trials, validate, validate_data
from app.research_agent.workflow import start, observe, validate_submission
from app.research_agent.access import check
from app.api.strategy_lab import BacktestRequest
from tests.test_phase52_saved_runs_and_chart_series import HoldToEnd
from tests.test_market_concepts import bars
from tests.test_backtest_jobs import wait_for


@pytest.fixture
def research(tmp_path,monkeypatch):
    class Strategy(HoldToEnd):
        spec=replace(HoldToEnd.spec,key='trial_fixture',defaults={'skip':0},parameters=(ParameterSpec('skip','Skip','int',0,0,1,1),))
        def on_bar(self,ctx):
            if self.params['skip']:return None
            return super().on_bar(ctx)
    monkeypatch.setitem(strategy_registry._items,Strategy.spec.key,Strategy)
    db=Database(tmp_path/'db');db.initialize();repo=ResearchRepository(db)
    class Service(BacktestService):
        changed=False
        def prepare(self,payload,**kwargs):
            validate_submission(db,payload)
            begin=pd.Timestamp('2026-01-02T14:30Z');end=pd.Timestamp('2026-01-02T14:37Z')
            check('QQQ','1m',begin,end,'fixture')
            frame=bars()
            if self.changed:frame.loc[0,'volume']+=1
            return dict(strategy_key=Strategy.spec.key,symbols=['QQQ'],primary='1m',additional=[],session='regular',requested_session='regular',
                start=begin,end=end,delay=0,frames_by_symbol={'QQQ':{'1m':frame}},diagnostic_history={},diagnostic_warnings=[],providers={'QQQ':'fixture'},source_namespaces={'QQQ':'fixture'})
    service=Service(None,BacktestRunRepository(db));jobs=BacktestJobs(db,service,1)
    services=SimpleNamespace(database=db,backtest_jobs=jobs)
    project=repo.create('Actual trials',Strategy.spec.key,[dict(symbols=['QQQ'],timeframe='1m',start='2026-01-01',end='2026-01-03',state='DEVELOPMENT'),dict(symbols=['QQQ'],timeframe='1m',start='2027-01-01',end='2027-12-31',state='LOCKED_HOLDOUT')])
    payload=BacktestRequest(strategy_key=Strategy.spec.key,symbols=['QQQ'],start_date='2026-01-02',end_date='2026-01-02',primary_timeframe='1m',strategy_params={'skip':0}).model_dump()
    submitted=start(services,project['id'],payload)
    wait_for(lambda:jobs.get(submitted['baseline_job_id'])['status']=='completed')
    project=observe(services,project['id'])
    hypothesis=HypothesisRepository(db).register(project['id'],dict(request_key='test',description='Skip fixture',rationale='Deterministic fixture',feature='skip',
        discovery_dataset_ids=[project['datasets'][0]['id']],expected_result='Fewer trades',falsification='Same trades',researcher_reasoning='Fixture',devils_advocate_objections='Removal of winners',axes=[dict(parameter='skip',values=[0,1])]))
    yield db,repo,project,hypothesis,jobs,service
    jobs.close()


def terminal(trials,id):return trials.get(id)['status'] in {'COMPLETED','FAILED','PAUSED','BUDGET_EXHAUSTED'}


def test_real_control_then_variants_without_frontend_and_immutable_baseline(research):
    db,_,project,hypothesis,jobs,service=research;trials=Trials(db)
    before=service.runs.get(project['baseline_run_id'])
    trial=trials.approve(project['id'],hypothesis['id'])
    assert trials.approve(project['id'],hypothesis['id'])['id']==trial['id']
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id'])
    assert result['status']=='COMPLETED',result.get('error')
    assert result['control_parity'] is True
    assert [c['role'] for c in result['cells']]==['control','variant','variant']
    assert result['cells'][2]['comparison']['removed']['n']>0
    assert result['cells'][1]['comparison']['control_parity']
    assert result['verdict']=='DEVELOPMENT_REVIEW_REQUIRED'
    assert len(service.runs.list())==4
    assert service.runs.get(project['baseline_run_id'])==before


def test_data_change_stops_before_control_engine_and_blocks_variants(research):
    db,_,project,hypothesis,_,service=research;service.changed=True;trials=Trials(db)
    trial=trials.approve(project['id'],hypothesis['id'])
    wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id'])
    assert result['status']=='PAUSED' and result['control_parity'] is None
    assert all(c['status']=='PENDING' for c in result['cells'][1:])
    assert len(service.runs.list())==1


def test_control_mismatch_never_releases_variants(research):
    db,_,project,hypothesis,_,service=research;trials=Trials(db)
    # Perturb saved baseline, not execution: control gate must detect it.
    with db.connect() as c:
        row=c.execute('SELECT result_json FROM backtest_runs WHERE id=?',(project['baseline_run_id'],)).fetchone();result=json.loads(row[0]);result['metrics']['fixture_changed']=True
        c.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',(json.dumps(result),project['baseline_run_id']))
    trial=trials.approve(project['id'],hypothesis['id']);wait_for(lambda:terminal(trials,trial['id']))
    result=trials.get(trial['id'])
    assert result['status']=='FAILED' and result['verdict']=='CONTROL_MISMATCH'
    assert len(service.runs.list())==2


def test_pause_resume_and_payload_forgery_rejected(research):
    db,_,project,hypothesis,jobs,service=research;trials=Trials(db)
    jobs.trial_coordinator.close()
    trial=trials.approve(project['id'],hypothesis['id'])
    trials.transition(trial['id'],'pause',jobs)
    with pytest.raises(ValueError):validate(db,trial['cells'][0]['payload'])
    resumed=trials.transition(trial['id'],'resume',jobs)
    forged={**resumed['cells'][0]['payload'],'start_date':'2027-01-01'}
    with pytest.raises(ValueError,match='Payload differs'):validate(db,forged)
    with pytest.raises(ValueError,match='Control parity'):validate(db,resumed['cells'][1]['payload'])
    jobs.trial_coordinator.tick()
    wait_for(lambda:any(j['payload'].get('research_trial_id') for j in jobs.list()))
    wait_for(lambda:next(j for j in jobs.list() if j['payload'].get('research_trial_id'))['status']=='completed')
    jobs.trial_coordinator.tick()
    assert trials.get(trial['id'])['control_parity'] is True


def test_budget_exhaustion_rejects_approval_without_queue(research):
    db,_,project,hypothesis,jobs,_=research;trials=Trials(db)
    with db.connect() as c:
        document=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0]);document['research_budget']['max_trial_runs']=2
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(document),project['id']))
    with pytest.raises(ValueError,match='budget'):trials.approve(project['id'],hypothesis['id'])
    assert not trials.list(project['id']) and len(jobs.list())==1


def test_restart_recovers_completed_control_without_duplicate_simulations(research):
    db,_,project,hypothesis,jobs,service=research;trials=Trials(db)
    jobs.trial_coordinator.close()
    trial=trials.approve(project['id'],hypothesis['id']);jobs.trial_coordinator.tick()
    wait_for(lambda:any(j['payload'].get('research_trial_id') and j['status']=='completed' for j in jobs.list()))
    jobs.close()
    restarted=BacktestJobs(db,service,1)
    try:
        wait_for(lambda:terminal(trials,trial['id']))
        assert trials.get(trial['id'])['status']=='COMPLETED'
        assert len(service.runs.list())==4
        assert len(restarted.list())==4
    finally:restarted.close()


def test_explicit_retry_preserves_cells_and_spends_one_more_attempt(research):
    db,_,project,hypothesis,jobs,service=research;trials=Trials(db);service.changed=True
    trial=trials.approve(project['id'],hypothesis['id']);wait_for(lambda:terminal(trials,trial['id']))
    old=trials.get(trial['id']);assert old['status']=='PAUSED'
    service.changed=False
    resumed=trials.transition(trial['id'],'resume',jobs)
    assert resumed['reserved_runs']==old['reserved_runs']+1
    assert resumed['cells'][0]['attempt']==1 and resumed['cells'][1]['attempt']==0
    wait_for(lambda:terminal(trials,trial['id']))
    assert trials.get(trial['id'])['status']=='COMPLETED'
    assert len(service.runs.list())==4


def test_active_time_budget_exhaustion_never_submits_cells(research):
    db,_,project,hypothesis,jobs,service=research;trials=Trials(db);jobs.trial_coordinator.close()
    trial=trials.approve(project['id'],hypothesis['id'])
    trial['active_since']-=100000
    with db.connect() as c:c.execute('UPDATE agent_trials SET document=? WHERE id=?',(json.dumps(trial),trial['id']))
    jobs.trial_coordinator.tick()
    assert trials.get(trial['id'])['status']=='BUDGET_EXHAUSTED'
    assert len(jobs.list())==1
    with pytest.raises(ValueError):trials.transition(trial['id'],'resume',jobs)


def test_api_requires_explicit_approval_and_does_not_accept_configuration(research):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    db,_,project,hypothesis,jobs,_=research;jobs.trial_coordinator.close()
    app=FastAPI();app.state.services=SimpleNamespace(database=db,backtest_jobs=jobs);app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        path='/api/strategy-lab/research-agent/'+project['id']+'/hypotheses/'+hypothesis['id']+'/approve'
        assert client.post(path,json={}).status_code==422
        body={'acknowledgement':'Run the frozen control and development variants'}
        assert client.post(path,json={**body,'risk_value':999}).status_code==422
        response=client.post(path,json=body)
        assert response.status_code==200,response.text
        assert len(jobs.list())==1  # coordinator stopped; approval itself is durable only
        assert client.get('/api/strategy-lab/research-agent/'+project['id']+'/trials').json()['reserved_runs']==3
