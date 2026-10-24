from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx
import pytest
from pydantic import BaseModel

from app.storage.database import Database
from app.research_agent.acceptance_spending import AcceptanceSpending
from app.research_agent.llm import OpenAICommitteeModel, ModelFailure
from app.research_agent.spending import quote


def settings(cap=5):
    return SimpleNamespace(research_llm_enabled=True,research_llm_api_key='fixture-secret',research_llm_model='fixture',
        research_llm_max_output_tokens=1000,research_llm_input_usd_per_million=1,
        research_llm_output_usd_per_million=2,research_llm_acceptance_budget_usd=cap)


@pytest.fixture
def db(tmp_path):return Database(tmp_path/'acceptance.db')


def test_concurrent_reservations_and_restart_cannot_exceed_allowance(db):
    budget=AcceptanceSpending(db,5);pricing=quote(settings())
    def reserve(_):
        try:return budget.reserve(pricing)
        except ValueError:return None
    with ThreadPoolExecutor(8) as pool:results=list(pool.map(reserve,range(40)))
    assert sum(r is not None for r in results)==19
    report=AcceptanceSpending(db,5).report()
    assert report['reserved_usd']==4.788 and report['unknown_usage_calls']==19
    assert report['usage_estimate_usd']==0 and not report['invoice_verified']
    with pytest.raises(ValueError):AcceptanceSpending(db,4)
    with pytest.raises(ValueError):AcceptanceSpending(db,6)


class Response(BaseModel):answer: str


def test_real_adapter_mock_transport_reserves_before_dispatch_and_retains_cap(db):
    requests=[]
    def handle(request):
        requests.append(request)
        assert AcceptanceSpending(db,.252).report()['reserved_usd']==.252
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"answer":"ok"}'}]}],
                                     'usage':{'input_tokens':100,'output_tokens':10}})
    adapter=OpenAICommitteeModel(settings(.252),httpx.MockTransport(handle),database=db)
    assert adapter.generate('test','',{},Response)[0]=={'answer':'ok'}
    report=adapter.acceptance_budget().report()
    assert report['usage_estimate_usd']==.00012 and report['reserved_usd']==.252
    # Removing the env cap, recreating the adapter or using another project cannot reset it.
    adapter=OpenAICommitteeModel(settings(None),httpx.MockTransport(handle),database=db)
    with pytest.raises(ModelFailure,match='budget_blocked'):adapter.generate('test','',{},Response)
    assert len(requests)==1


@pytest.mark.parametrize('status',[401,429,500])
def test_failed_calls_remain_reserved_without_retries(db,status):
    requests=[]
    def handle(request):requests.append(request);return httpx.Response(status,json={'secret':'NEVER_PRINT'})
    adapter=OpenAICommitteeModel(settings(.252),httpx.MockTransport(handle),database=db)
    with pytest.raises(ModelFailure):adapter.generate('test','',{},Response)
    assert adapter.acceptance_budget().report()['unknown_usage_calls']==1
    with pytest.raises(ModelFailure):adapter.generate('test','',{},Response)
    assert len(requests)==1


def test_missing_storage_and_pricing_fail_before_transport(db):
    requests=[];transport=httpx.MockTransport(lambda r:requests.append(r))
    adapter=OpenAICommitteeModel(settings(),transport)
    with pytest.raises(ModelFailure,match='storage_required'):adapter.generate('test','',{},Response)
    config=settings();config.research_llm_input_usd_per_million=0
    with pytest.raises(ModelFailure,match='budget_blocked'):OpenAICommitteeModel(config,transport,database=db).generate('test','',{},Response)
    assert requests==[]


def test_usage_overrun_blocks_later_calls(db):
    budget=AcceptanceSpending(db,5);identifier=budget.reserve(quote(settings()))
    with pytest.raises(ValueError):budget.finish(identifier,{'input_tokens':250001,'output_tokens':1})
    with pytest.raises(ValueError,match='further calls blocked'):budget.reserve(quote(settings()))


def test_status_endpoint_is_safe_read_only_and_does_not_call_provider(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(database=db,settings=settings())
    with TestClient(app) as client:
        reply=client.get('/strategy-lab/research-agent/model-status')
        assert reply.status_code==200
        body=reply.json()
        assert body['configured'] and body['model']=='fixture'
        assert body['configured_acceptance_limit_usd']==5 and body['acceptance_spending'] is None
        assert not body['connection_tested'] and 'fixture-secret' not in reply.text
    with db.connect() as c:assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_acceptance_allowance'").fetchone()
