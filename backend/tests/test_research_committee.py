from copy import deepcopy
from types import SimpleNamespace
import json
import httpx
import pytest
from tests.test_research_hypotheses import registered
from app.research_agent.committee import Committee, Researcher
from app.research_agent.hypotheses import HypothesisRepository
from app.research_agent.llm import OpenAICommitteeModel, ModelFailure, strict_schema


class FakeModel:
    def __init__(self, proposal, fault=None):self.proposal=proposal;self.calls=[];self.fault=fault
    def status(self):return {'configured':True,'model':'fixture','provider':'fixture'}
    def generate(self,role,instructions,evidence,model):
        self.calls.append((role,deepcopy(evidence)))
        if self.fault:return self.fault(role),{}
        p=self.proposal
        if role=='Researcher':result={k:p[k] for k in ('description','rationale','feature','expected_result','falsification','axes')};result.update(decision='PROPOSE',evidence_refs=['summary'])
        elif role=='Devil':result=dict(verdict='CHALLENGE',concerns=['Protect winners'],alternative_explanations=['Sample noise'],required_checks=['Compare periods'],evidence_refs=['large_winners'])
        else:result=dict(decision='RECOMMEND_EXPERIMENT',explanation='Test, do not promote',evidence_refs=['summary'])
        return result,{'input_tokens':100,'output_tokens':100,'total_tokens':200}


def test_committee_sequential_readonly_idempotent_and_explicit_preregistration(registered):
    db,repo,project,proposal=registered;model=FakeModel(proposal);service=Committee(db,model)
    result=service.review(project['id'],'one')
    assert result['status']=='COMPLETED',result
    assert [r for r,_ in model.calls]==['Researcher','Devil','Manager']
    assert 'Researcher' in model.calls[1][1]['prior_roles']
    assert 'Devil' in model.calls[2][1]['prior_roles']
    assert not HypothesisRepository(db).list(project['id'])
    assert service.review(project['id'],'one')==result and len(model.calls)==3
    stored=service.preregister(project['id'],result['id'])
    assert stored['committee_review_id']==result['id'] and stored['authorship']=='committee_user_approved'
    assert not stored['execution_enabled']
    assert service.preregister(project['id'],result['id'])['id']==stored['id']
    assert 'LOCKED_HOLDOUT' not in json.dumps(model.calls)
    assert '2025-01-01' not in json.dumps(model.calls)
    assert len(Committee(db,model).list(project['id']))==1


@pytest.mark.parametrize('fault',[lambda role:{'shell':'unsafe'},lambda role:{'decision':'PROPOSE','description':'x','rationale':'x','feature':'x','expected_result':'x','falsification':'x','evidence_refs':['invented'],'axes':[]}])
def test_malformed_or_uncited_output_stops_without_side_effects(registered,fault):
    db,_,project,proposal=registered;model=FakeModel(proposal,fault);service=Committee(db,model)
    result=service.review(project['id'],'bad')
    assert result['status']=='FAILED' and len(model.calls)==1
    assert not HypothesisRepository(db).list(project['id'])
    assert service.review(project['id'],'bad')['status']=='FAILED' and len(model.calls)==1
    with pytest.raises(ValueError):service.preregister(project['id'],result['id'])


def test_budget_stops_calls_and_restart_cannot_reset_it(registered):
    db,_,project,proposal=registered;model=FakeModel(proposal);service=Committee(db,model)
    for index in range(4):assert service.review(project['id'],str(index))['status']=='COMPLETED'
    with pytest.raises(ValueError,match='budget'):Committee(db,model).review(project['id'],'over')
    assert len(model.calls)==12


def test_pause_during_call_stops_remaining_roles(registered):
    db,repo,project,proposal=registered
    class Pausing(FakeModel):
        def generate(self,*args):
            result=super().generate(*args);repo.transition(project['id'],'PAUSED');return result
    model=Pausing(proposal);result=Committee(db,model).review(project['id'],'pause')
    assert result['status']=='FAILED' and result['error']=='project_not_active' and len(model.calls)==1


def settings():
    return SimpleNamespace(research_llm_enabled=True,research_llm_api_key='SECRET_FIXTURE',research_llm_model='fixture',research_llm_max_output_tokens=1024)


def test_adapter_request_has_no_tools_or_storage_and_parses_schema(registered):
    _,_,_,proposal=registered;fake=FakeModel(proposal)
    output,_=fake.generate('Researcher','',{},Researcher)
    def handle(request):
        assert str(request.url)=='https://api.openai.com/v1/responses'
        body=json.loads(request.content)
        assert body['store'] is False and 'tools' not in body
        assert body['text']['format']['strict'] and body['max_output_tokens']==1024
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(output)}]}],'usage':{'input_tokens':10,'output_tokens':20,'total_tokens':30}})
    adapter=OpenAICommitteeModel(settings(),httpx.MockTransport(handle))
    result,usage=adapter.generate('Researcher','Instructions',{'summary':{}},Researcher)
    assert result['decision']=='PROPOSE' and usage['total_tokens']==30
    schema=strict_schema(Researcher)
    assert set(schema['required'])==set(schema['properties']) and schema['additionalProperties'] is False


@pytest.mark.parametrize('status',[302,401,429,500])
def test_provider_errors_never_echo_secrets_or_retry(status):
    calls=[]
    def handle(request):calls.append(request);return httpx.Response(status,json={'error':'SECRET_FIXTURE'},headers={'Location':'https://untrusted.invalid'})
    adapter=OpenAICommitteeModel(settings(),httpx.MockTransport(handle))
    with pytest.raises(ModelFailure) as failure:adapter.generate('Researcher','',{},Researcher)
    assert 'SECRET' not in str(failure.value) and len(calls)==1


def test_expired_review_stays_interrupted_without_reissuing_calls(registered):
    db,_,project,proposal=registered;model=FakeModel(proposal);service=Committee(db,model)
    result=service.review(project['id'],'crashed');result.update(status='RUNNING',deadline='2000-01-01T00:00:00+00:00')
    with db.connect() as c:c.execute('UPDATE agent_reviews SET document=? WHERE id=?',(json.dumps(result),result['id']))
    assert Committee(db,model).review(project['id'],'crashed')['status']=='INTERRUPTED'
    assert len(model.calls)==3


def test_api_requires_consent_and_returns_persisted_review(registered,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import app.api.research_agent as api
    db,_,project,proposal=registered;model=FakeModel(proposal);committee=Committee(db,model)
    monkeypatch.setattr(api,'committee_service',lambda services:committee)
    app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(api.router,prefix='/api')
    with TestClient(app) as client:
        path='/api/strategy-lab/research-agent/'+project['id']+'/committee'
        assert client.post(path,json={'request_key':'one'}).status_code==422
        assert not model.calls
        response=client.post(path,json={'request_key':'one','consent':'Send development summaries to the configured model'})
        assert response.status_code==200 and response.json()['status']=='COMPLETED'
        assert client.get(path).json()['reserved_calls']==3
        assert len(client.get(path).json()['items'])==1


def test_incomplete_configuration_and_locked_baseline_make_zero_calls(registered):
    db,repo,project,proposal=registered;model=FakeModel(proposal)
    adapter=OpenAICommitteeModel(SimpleNamespace(research_llm_enabled=False,research_llm_api_key='',research_llm_model=''))
    with pytest.raises(ValueError,match='not configured'):Committee(db,adapter).review(project['id'],'off')
    # Corrupted/misassigned saved-run reference still must not leak held-out results.
    from app.storage.backtest_run_repository import BacktestRunRepository
    saved=BacktestRunRepository(db).create(config=dict(strategy_key=project['strategy_key'],symbols=['QQQ'],start_date='2025-01-02',end_date='2025-01-02',primary_timeframe='1m'),result={'secret_holdout':'NEVER_SEND'})
    with db.connect() as c:
        document=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project['id'],)).fetchone()[0]);document['baseline_run_id']=saved['id']
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(document),project['id']))
    with pytest.raises(ValueError,match='Holdout'):Committee(db,model).review(project['id'],'held')
    assert model.calls==[]


def test_concurrent_duplicate_review_only_calls_model_once(registered):
    from threading import Event
    from concurrent.futures import ThreadPoolExecutor
    db,_,project,proposal=registered;entered=Event();release=Event()
    class Blocking(FakeModel):
        def generate(self,*args):
            entered.set();assert release.wait(5);return super().generate(*args)
    model=Blocking(proposal);service=Committee(db,model)
    with ThreadPoolExecutor(2) as pool:
        task=pool.submit(service.review,project['id'],'same')
        try:
            assert entered.wait(5)
            duplicate=service.review(project['id'],'same')
            assert duplicate['status']=='RUNNING'
        finally:release.set()
        assert task.result()['id']==duplicate['id']
    assert len(model.calls)==3
