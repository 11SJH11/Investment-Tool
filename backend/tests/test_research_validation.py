import json
import pandas as pd
import pytest
from tests.test_research_trials import research
from tests.test_research_feedback import completed
from tests.test_backtest_jobs import wait_for
from app.research_agent.candidates import Candidates
from app.research_agent.validation import Validations, Criteria, validate, verdict
from app.research_agent.access import scope, check


@pytest.fixture
def frozen(research,monkeypatch):
    trial=completed(research);db,repo,project,hypothesis,jobs,service=research
    candidate=Candidates(db).freeze(project['id'],trial['id'],1,'Validation fixture')
    original=service.prepare
    def prepare(payload,**kwargs):
        inputs=original(payload,**kwargs)
        if payload.get('research_validation_id'):
            delta=pd.Timedelta(days=365)
            inputs['start']+=delta;inputs['end']+=delta
            check('QQQ','1m',inputs['start'],inputs['end'],'fixture')
            inputs['frames_by_symbol']['QQQ']['1m']['timestamp']+=delta
        return inputs
    monkeypatch.setattr(service,'prepare',prepare)
    return research,candidate


def approve(frozen):
    (db,_,project,_,_,_),candidate=frozen
    service=Validations(db)
    return service,service.approve(project['id'],candidate['id'],project['datasets'][1]['id'],Criteria().model_dump())


def test_validation_executes_frozen_pair_once_and_keeps_candidate_immutable(frozen):
    service,grant=approve(frozen);research,candidate=frozen;db,repo,project,_,jobs,_=research
    wait_for(lambda:service.get(grant['id'])['status']!='ACTIVE')
    result=service.get(grant['id']);assert result['status']=='COMPLETED',result
    assert result['comparison']['data_equivalent']
    assert result['verdict']=='INSUFFICIENT_EVIDENCE'
    assert Candidates(db).list(project['id'])[0]==candidate
    assert repo.get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'
    assert len([j for j in jobs.list() if j['payload'].get('research_validation_id')])==2
    assert service.approve(project['id'],candidate['id'],grant['dataset_id'],grant['criteria'])['id']==grant['id']
    with pytest.raises(ValueError,match='immutable'):service.approve(project['id'],candidate['id'],grant['dataset_id'],{'minimum_trades':1})


def test_grant_does_not_unlock_ordinary_research_or_allow_payload_edits(frozen):
    research,_=frozen;db,_,project,_,jobs,_=research;jobs.trial_coordinator.close()
    service,grant=approve(frozen)
    begin=pd.Timestamp('2027-01-02T14:30Z');end=begin+pd.Timedelta(minutes=7)
    with scope(db,project['id']):
        with pytest.raises(ValueError,match='outside'):check('QQQ','1m',begin,end)
    with scope(db,project['id'],grant['id']):
        check('QQQ','1m',begin,end)
        with pytest.raises(ValueError,match='outside'):check('QQQ','1m',begin+pd.Timedelta(days=400),end+pd.Timedelta(days=400))
    with pytest.raises(ValueError,match='Payload differs'):validate(db,{**grant['cells'][0]['payload'],'strategy_params':{'skip':99}})


def test_validation_budget_rejection_does_not_consume_dataset(frozen):
    (db,repo,project,_,_,_),_=frozen
    with db.connect() as c:
        row=c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone();p=json.loads(row[0]);p['research_budget']['max_trial_runs']=4
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
    with pytest.raises(ValueError,match='budget'):approve(frozen)
    assert repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'


def test_project_pause_stops_validation_without_restoring_unseen_state(frozen):
    (db,repo,project,_,jobs,_),_=frozen;jobs.trial_coordinator.close();service,grant=approve(frozen)
    repo.transition(project['id'],'PAUSED');service.tick(jobs)
    assert service.get(grant['id'])['status']=='FAILED'
    assert repo.get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'
    assert not any(j['payload'].get('research_validation_id') for j in jobs.list())


def test_validation_classification_requires_observed_metrics_and_sample():
    criteria=Criteria(minimum_trades=30,minimum_average_r=.1,minimum_profit_factor_r=1.2).model_dump()
    assert verdict({'n':30,'average_r':.1,'profit_factor_r':1.2},criteria)=='VALIDATION_PASS'
    assert verdict({'n':30,'average_r':.09,'profit_factor_r':2},criteria)=='VALIDATION_FAIL'
    assert verdict({'n':29,'average_r':1,'profit_factor_r':2},criteria)=='INSUFFICIENT_EVIDENCE'
    assert verdict({'n':30,'average_r':1,'profit_factor_r':None},criteria)=='INSUFFICIENT_EVIDENCE'


def test_validation_data_change_blocks_candidate_engine_and_preserves_baseline(frozen):
    research,_=frozen;db,_,_,_,jobs,backtest=research;jobs.trial_coordinator.close()
    service,grant=approve(frozen)
    service.tick(jobs)
    wait_for(lambda: any(j['payload'].get('research_validation_id') and j['status']=='completed' for j in jobs.list()))
    service.tick(jobs)
    backtest.changed=True
    service.tick(jobs)
    wait_for(lambda:any(j['payload'].get('research_validation_cell')==1 and j['status']=='failed' for j in jobs.list()))
    service.tick(jobs)
    assert service.get(grant['id'])['status']=='FAILED'
    assert len([r for r in backtest.runs.list() if r['test_role']=='validation'])==1


def test_validation_recovery_reuses_completed_job_and_api_requires_consent(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.research_agent import router
    research,candidate=frozen;db,_,project,_,jobs,_=research;jobs.trial_coordinator.close()
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/candidates/'+candidate['id']+'/validate'
    payload={'dataset_id':project['datasets'][1]['id'],'criteria':Criteria().model_dump()}
    with TestClient(app) as client:
        assert client.post(path,json=payload).status_code==422
        payload['acknowledgement']='Run this frozen candidate on the selected dataset; it will no longer be unseen'
        response=client.post(path,json=payload);assert response.status_code==200,response.text
        grant=response.json()
    service=Validations(db);service.tick(jobs)
    wait_for(lambda:any(j['payload'].get('research_validation_id') and j['status']=='completed' for j in jobs.list()))
    recovered=Validations(db);recovered.tick(jobs);recovered.tick(jobs)
    wait_for(lambda:sum(j['payload'].get('research_validation_id')==grant['id'] and j['status']=='completed' for j in jobs.list())==2)
    recovered.tick(jobs);recovered.tick(jobs)
    assert recovered.get(grant['id'])['status']=='COMPLETED'
    assert len([j for j in jobs.list() if j['payload'].get('research_validation_id')])==2


def test_modified_frozen_snapshot_cannot_consume_holdout(frozen):
    (db,repo,project,_,_,_),candidate=frozen
    with db.connect() as c:
        row=c.execute('SELECT document FROM agent_candidates WHERE id=?',(candidate['id'],)).fetchone();changed=json.loads(row[0])
        changed['snapshot']['configuration']['strategy_params']['skip']=1
        c.execute('UPDATE agent_candidates SET document=? WHERE id=?',(json.dumps(changed),candidate['id']))
    with pytest.raises(ValueError,match='snapshot changed'):approve(frozen)
    assert repo.get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'
