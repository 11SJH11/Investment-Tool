import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.storage.research_retention import ResearchRunProtected
from tests.test_strategy_source_archive import repository


def test_ordinary_run_deletion_and_missing_run_still_work(repository):
    run=repository.create(config={},result={})
    repository.delete(run['id'])
    with pytest.raises(ValueError,match='not found'):repository.delete(run['id'])


@pytest.mark.parametrize('key',['research_project_id','research_trial_id','research_validation_id'])
def test_owned_run_cannot_be_deleted_before_coordinator_records_it(repository,key):
    run=repository.create(config={key:'fixture'},result={})
    with pytest.raises(ResearchRunProtected):repository.delete(run['id'])
    assert repository.get(run['id'])==run


@pytest.mark.parametrize('table,document',[
    ('agent_projects',{'state':'ARCHIVED','baseline_run_id':1}),
    ('agent_projects',{'analyses':{'1':{'summary':{}}}}),
    ('agent_trials',{'cells':[{'run_id':1}]}),
    ('agent_candidates',{'parent_run_id':1}),
    ('agent_validations',{'cells':[{'run_id':1}]}),
    ('agent_concept_audits',{'baseline_run_id':1}),
    ('agent_decisions',{'evidence':{'candidate_run_id':1}}),
])
def test_existing_references_remain_protected_including_archived_projects(repository,table,document):
    run=repository.create(config={},result={});assert run['id']==1
    with repository.database.connect() as c:
        c.execute(f'CREATE TABLE {table}(document TEXT)')
        c.execute(f'INSERT INTO {table} VALUES (?)',(json.dumps(document),))
    with pytest.raises(ResearchRunProtected):repository.delete(run['id'])
    unrelated=repository.create(config={},result={});repository.delete(unrelated['id'])
    assert repository.get(run['id'])==run


def test_delete_api_returns_conflict_without_removing_evidence(repository):
    from app.api.strategy_lab import router
    run=repository.create(config={'research_project_id':'fixture'},result={})
    app=FastAPI();app.include_router(router)
    app.state.services=SimpleNamespace(backtest=SimpleNamespace(delete_run=repository.delete))
    with TestClient(app) as client:
        response=client.delete('/strategy-lab/runs/'+str(run['id']))
    assert response.status_code==409 and 'research evidence' in response.json()['detail']
    assert repository.get(run['id'])==run
