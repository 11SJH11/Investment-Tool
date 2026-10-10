from copy import deepcopy
import json
import pytest
from tests.test_research_trials import research
from tests.test_research_committee import FakeModel
from tests.test_backtest_jobs import wait_for
from app.research_agent.loop import ResearchLoop
from app.research_agent.trials import Trials, active
from app.research_agent.hypotheses import HypothesisRepository


def controller(research, cycles=1):
    db,_,project,hypothesis,jobs,_=research
    proposal=deepcopy(hypothesis);proposal['axes'][0]['values']=[1]
    model=priced_model(db,project,proposal);loop=ResearchLoop(db,jobs,model,start_thread=False)
    document=loop.start(project['id'],cycles)
    return loop,model,document


def test_authorized_loop_runs_real_control_variants_and_stops_at_cycle_limit(research):
    loop,model,document=controller(research);pid=document['project_id']
    loop.tick();assert loop.get(pid)['phase']=='APPROVE'
    hypothesis=HypothesisRepository(loop.database).list(pid)[-1]
    assert hypothesis['authorship']=='committee_loop_authorized'
    loop.tick();assert loop.get(pid)['phase']=='WAIT'
    trial_id=loop.get(pid)['trial_id']
    wait_for(lambda:Trials(loop.database).get(trial_id)['status']=='COMPLETED')
    loop.tick();loop.tick()
    assert loop.get(pid)['status']=='COMPLETED' and len(model.calls)==3
    loop.tick();assert len(model.calls)==3
    assert len(loop.get(pid)['cycles'])==1
    with pytest.raises(ValueError,match='cannot be reset'):loop.start(pid,1)


def test_next_cycle_sees_completed_trial_and_stops_duplicate_experiment(research):
    loop,model,document=controller(research,2);pid=document['project_id']
    loop.tick();loop.tick();trial_id=loop.get(pid)['trial_id']
    wait_for(lambda:Trials(loop.database).get(trial_id)['status']=='COMPLETED')
    loop.tick();loop.tick()
    assert loop.get(pid)['status']=='STOPPED'
    assert 'already registered' in loop.get(pid)['reason']
    assert 'trial/'+trial_id in model.calls[3][1]['evidence']
    assert len(Trials(loop.database).list(pid))==1


def test_pause_revokes_trial_authorization_and_no_model_retry(research):
    loop,model,document=controller(research);pid=document['project_id']
    loop.jobs.trial_coordinator.close()
    loop.tick();loop.tick();trial=Trials(loop.database).get(loop.get(pid)['trial_id'])
    assert active(loop.database,trial['cells'][0]['payload'])
    loop.pause(pid)
    assert not active(loop.database,trial['cells'][0]['payload'])
    loop.tick();assert len(model.calls)==3
    assert Trials(loop.database).get(trial['id'])['status']=='PAUSED'


def test_pause_inside_model_call_prevents_following_roles_and_registration(research):
    loop,model,document=controller(research);pid=document['project_id'];generate=model.generate
    def pausing(*args):
        result=generate(*args);loop.pause(pid);return result
    model.generate=pausing;loop.tick()
    assert loop.get(pid)['status']=='PAUSED' and len(model.calls)==1
    assert len(HypothesisRepository(loop.database).list(pid))==1
    assert not Trials(loop.database).list(pid)


def test_restart_recovers_registered_hypothesis_without_duplicate_calls(research):
    loop,model,document=controller(research);pid=document['project_id'];loop.tick()
    # Crash after registration but before saving the next loop phase.
    with loop.database.connect() as c:
        saved=loop.get(pid);saved['phase']='REVIEW'
        c.execute('UPDATE agent_loops SET document=? WHERE project_id=?',(json.dumps(saved),pid))
    restarted=ResearchLoop(loop.database,loop.jobs,model,start_thread=False);restarted.tick()
    assert restarted.get(pid)['phase']=='APPROVE' and len(model.calls)==3
    assert len(HypothesisRepository(loop.database).list(pid))==2


def test_loop_api_requires_explicit_consent(research):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.research_agent import router
    db,_,project,hypothesis,jobs,_=research
    service=ResearchLoop(db,jobs,priced_model(db,project,hypothesis),start_thread=False)
    app=FastAPI();app.state.services=SimpleNamespace(research_loop=service);app.include_router(router)
    path='/strategy-lab/research-agent/'+project['id']+'/loop'
    with TestClient(app) as client:
        assert client.post(path,json={'max_cycles':1}).status_code==422
        response=client.post(path,json={'max_cycles':1,'acknowledgement':'Authorize bounded model reviews and development backtests'})
        assert response.status_code==200,response.text
        assert client.get(path).json()['status']=='ACTIVE'
        assert client.post(path+'/pause').json()['status']=='PAUSED'


def test_resume_preserves_cycles_and_recovers_paused_trial(research):
    loop,model,document=controller(research);pid=document['project_id']
    loop.jobs.trial_coordinator.close();loop.tick();loop.tick()
    trial_id=loop.get(pid)['trial_id'];loop.pause(pid);loop.resume(pid)
    assert loop.get(pid)['max_cycles']==1 and loop.get(pid)['cycles']==[]
    assert Trials(loop.database).get(trial_id)['status']=='ACTIVE'
    assert len(model.calls)==3


def test_disabled_model_cannot_authorize_and_call_budget_stops_new_review(research):
    loop,model,document=controller(research);pid=document['project_id']
    with loop.database.connect() as c:
        row=c.execute('SELECT document FROM agent_projects WHERE id=?',(pid,)).fetchone();project=json.loads(row[0])
        project['research_budget']['max_llm_calls']=0
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(project),pid))
    loop.tick()
    assert loop.get(pid)['status']=='STOPPED' and not model.calls
    assert not Trials(loop.database).list(pid)


def test_transactional_authorization_rejects_paused_loop_registration_and_approval(research):
    loop,model,document=controller(research);pid=document['project_id'];loop.tick()
    h=HypothesisRepository(loop.database).list(pid)[-1]
    loop.pause(pid)
    with pytest.raises(ValueError,match='not active'):
        Trials(loop.database).approve(pid,h['id'],loop_id=document['id'])
    with pytest.raises(ValueError,match='not active'):
        loop.committee.preregister(pid,loop.get(pid)['review_id'],loop_id=document['id'])
    assert not Trials(loop.database).list(pid)


def priced_model(db,project,proposal):
    with db.connect() as c:
        row=c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone();stored=json.loads(row[0])
        stored['research_budget']['max_llm_spend_usd']=10
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(stored),project['id']))
    model=FakeModel(proposal)
    model.status=lambda:{'configured':True,'model':'fixture','provider':'fixture','pricing':{'model':'fixture','input_usd_per_million':1,'output_usd_per_million':1,'input_token_reservation':100000,'output_token_reservation':4096,'call_reservation_microusd':104096}}
    return model
