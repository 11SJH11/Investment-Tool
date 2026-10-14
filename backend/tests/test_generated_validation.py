"""Grant/lifecycle guards; real Docker execution is covered by campaign acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
from tests.test_research_trials import research
from app.research_agent.analysis import digest
from app.research_agent.generated_validation import approve, verified_candidate, KIND
from app.research_agent.sandbox_runs import SandboxRuns
from app.research_agent.validation import Validations, validate
from app.research_agent.candidates import Candidates


class DockerFixture:
    def __init__(self):self.cleanups=0
    def cleanup(self):self.cleanups+=1
    def image(self):return 'image'
    def close(self):pass


class DeferredThread:
    def __init__(self,**kwargs):self.kwargs=kwargs
    def start(self):pass
    def is_alive(self):return False
    def join(self,**kwargs):pass


@pytest.fixture
def generated(research,monkeypatch):
    db,repo,project,_,jobs,backtest=research
    jobs.trial_coordinator.close()
    runner=SandboxRuns(db,backtest,docker=DockerFixture())
    Candidates(db);Validations(db)
    baseline=backtest.runs.get(project['baseline_run_id'])
    source='INERT_SOURCE_NOT_PYTHON'
    trial={'candidate_id':'parent','status':'COMPLETED','reserved_runs':4,'request':{'control_parameters':{}}}
    snapshot=dict(configuration=baseline['config'],source=source,source_sha256=sha256(source.encode()).hexdigest(),
        dependencies={},parameters={},registry_key='inert',parent_hash='parent-hash',sandbox_id='development',
        evidence_sha256=digest(trial),provenance={'image_id':'image','dependency_sha256':sha256(b'{}').hexdigest()})
    parent=dict(id='parent',project_id=project['id'],snapshot_hash='parent-hash',snapshot={'hypothesis':{}})
    candidate=dict(id='generated',project_id=project['id'],kind='GENERATED_DEVELOPMENT',state='FROZEN_DEVELOPMENT',
        snapshot=snapshot,snapshot_hash=digest(snapshot))
    with db.connect() as c:
        for i,doc in enumerate((parent,candidate)):
            c.execute('INSERT INTO agent_candidates VALUES (?,?,?,?,?)',(doc['id'],project['id'],'fixture',i,json.dumps(doc)))
        c.execute('INSERT INTO agent_sandbox_runs VALUES (?,?,?,?)',('development',project['id'],'draft',json.dumps(trial)))
        c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',
            (project['id'],'generated_candidate_frozen',json.dumps({'candidate_id':candidate['id'],'snapshot_hash':candidate['snapshot_hash']})))
    # A synthetic immutable parent record is sufficient for grant tests. The full
    # parent/evidence/control path is exercised without this patch in real Docker.
    monkeypatch.setattr(Candidates,'verify_sandbox_parent',lambda *a:None)
    monkeypatch.setattr('app.research_agent.generated_validation.Thread',DeferredThread)
    yield runner,project,candidate
    runner.close()


def request(generated):
    runner,project,candidate=generated
    return approve(runner,project['id'],candidate['id'],project['datasets'][1]['id'],{})


def test_grant_is_candidate_bound_idempotent_and_never_dispatched_to_host(generated):
    runner,project,candidate=generated;grant=request(generated)
    assert grant['kind']==KIND and grant['reserved_runs']==4 and not grant['automatic_promotion']
    assert request(generated)==grant
    assert verified_candidate(runner.database,project['id'],candidate['id'])[0]==candidate
    assert next(d for d in ResearchRepository(runner.database).get(project['id'])['datasets'] if d['id']==grant['dataset_id'])['state']=='INSPECTED_VALIDATION'
    class ForbiddenQueue:
        def enqueue(self,*a):raise AssertionError('Generated code entered host queue')
    store=Validations(runner.database);store.tick(ForbiddenQueue())
    assert store.get(grant['id'])==grant
    with pytest.raises(ValueError,match='requires Docker'):store.advance(grant,ForbiddenQueue())
    with pytest.raises(ValueError,match='host job queue'):validate(runner.database,{'research_validation_id':grant['id'],'research_validation_cell':0})
    with pytest.raises(ValueError,match='immutable'):
        approve(runner,project['id'],candidate['id'],grant['dataset_id'],{'minimum_trades':1})


from app.research_agent.repository import ResearchRepository


@pytest.mark.parametrize('failure',['budget','image','snapshot','evidence','audit','busy','paused'])
def test_rejected_grant_never_consumes_dataset(generated,failure):
    runner,project,candidate=generated
    with runner.database.connect() as c:
        if failure in {'budget','paused'}:
            p=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0])
            if failure=='budget':p['research_budget']['max_trial_runs']=0
            else:p['state']='PAUSED'
            c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(p),project['id']))
        elif failure=='snapshot':
            candidate['snapshot']['source']='changed'
            c.execute('UPDATE agent_candidates SET document=? WHERE id=?',(json.dumps(candidate),candidate['id']))
        elif failure=='evidence':c.execute("UPDATE agent_sandbox_runs SET document=json_set(document,'$.tampered',1)")
        elif failure=='audit':c.execute("DELETE FROM agent_events WHERE action='generated_candidate_frozen'")
    if failure=='image':runner.docker.image=lambda:'different'
    if failure=='busy':runner.thread=SimpleNamespace(is_alive=lambda:True,join=lambda **kw:None)
    with pytest.raises(ValueError):request(generated)
    assert not Validations(runner.database).list(project['id'])
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='LOCKED_HOLDOUT'


def test_recovery_interrupts_only_generated_validation_without_restoring_holdout(generated):
    runner,project,_=generated;grant=request(generated)
    numeric={**grant,'id':'numeric','candidate_id':'numeric','kind':'NUMERIC'}
    with runner.database.connect() as c:
        c.execute('INSERT INTO agent_validations VALUES (?,?,?,?)',('numeric',project['id'],'numeric',json.dumps(numeric)))
    restarted=SandboxRuns(runner.database,runner.backtest,docker=DockerFixture())
    try:
        restarted.recover();restarted.recover()
        store=Validations(runner.database)
        assert store.get(grant['id'])['status']=='INTERRUPTED'
        assert store.get('numeric')['status']=='ACTIVE'
        assert restarted.docker.cleanups==1
        assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'
        assert request(generated)['status']=='INTERRUPTED'
    finally:restarted.close()


def test_cancel_is_scoped_and_stopped_execution_keeps_exposure(generated):
    from app.research_agent.generated_validation import execute
    runner,project,_=generated;grant=request(generated)
    with pytest.raises(ValueError,match='Unknown'):runner.cancel_validation('different',grant['id'])
    assert not runner.cancel_event.is_set()
    runner.cancel_validation(project['id'],grant['id'])
    execute(runner,deepcopy(grant))
    result=Validations(runner.database).get(grant['id'])
    assert result['status']=='CANCELLED' and result['error']=='CANCELLED'
    assert 'result' not in result
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'


def test_isolated_api_requires_consent_and_returns_grant(generated):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    runner,project,candidate=generated
    app=FastAPI();app.state.services=SimpleNamespace(database=runner.database,research_sandbox=runner);app.include_router(router)
    path=f"/strategy-lab/research-agent/{project['id']}/candidates/{candidate['id']}/validate-isolated"
    payload={'dataset_id':project['datasets'][1]['id']}
    with TestClient(app) as client:
        assert client.post(path,json=payload).status_code==422
        payload['acknowledgement']='Run this frozen candidate on the selected dataset; it will no longer be unseen'
        response=client.post(path,json=payload)
        assert response.status_code==200,response.text
        assert response.json()['kind']==KIND


@pytest.mark.parametrize('failure',['timeout','provider','paused'])
def test_failure_does_not_retry_or_restore_unseen_state(generated,monkeypatch,failure):
    from app.research_agent.generated_validation import execute
    runner,project,_=generated;grant=request(generated)
    monkeypatch.setattr('app.research_agent.trials.check_source',lambda *a:None)
    calls=[]
    def fail_prepare(*a,**kw):
        calls.append('prepare')
        raise ValueError('Fixture provider failure')
    monkeypatch.setattr(runner.backtest,'prepare',fail_prepare)
    if failure=='timeout':grant['deadline']=0
    if failure=='paused':ResearchRepository(runner.database).transition(project['id'],'PAUSED')
    execute(runner,deepcopy(grant))
    result=Validations(runner.database).get(grant['id'])
    assert result['status']=='FAILED' and 'result' not in result
    assert calls==(['prepare'] if failure=='provider' else [])
    assert request(generated)['id']==grant['id']
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'


def test_dispatch_failure_is_durable_and_does_not_retry(generated,monkeypatch):
    def fail_start(self):raise RuntimeError('No thread available')
    monkeypatch.setattr(DeferredThread,'start',fail_start)
    runner,project,_=generated;grant=request(generated)
    assert grant['status']=='FAILED' and grant['error']=='ISOLATED_VALIDATION_DISPATCH_FAILED_NO_AUTOMATIC_RETRY'
    assert request(generated)==grant
    assert ResearchRepository(runner.database).get(project['id'])['datasets'][1]['state']=='INSPECTED_VALIDATION'
