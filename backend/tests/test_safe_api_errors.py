from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from app.api.dependencies import get_services
from app.api.strategy_lab import router as strategy_router
from app.api.research import router as research_router
from app.api.data import router as data_router
from app.core.safe_errors import MissingHistoryError,ProviderUnavailableError
from app.storage.market_store import MarketCacheCorruption
from app.data.http import ProviderHttpError

SECRET='secret-password https://private.example/account/123 token=unsafe'
ROUTES=[
 ('GET','/market/bars?ticker=NQ1!&start=2026-09-01T00:00:00Z&end=2026-09-02T00:00:00Z',None),
 ('GET','/research/NQ1!/bars',None),
 ('POST','/research/NQ1!/chart-data',{}),
 ('GET','/research/NQ1!/indicator?key=ema',None),
 ('GET','/strategy-lab/replay/bars?symbol=NQ1!&replay_date=2026-09-01',None),
 ('GET','/strategy-lab/replay/indicator?symbol=NQ1!&replay_date=2026-09-01&key=ema',None),
 ('GET','/strategy-lab/audit-bars?symbol=NQ1!',None),
 ('POST','/strategy-lab/backtest',{'strategy_key':'fixture','symbols':['NQ1!'],'start_date':'2026-09-01','end_date':'2026-09-02'}),
]
@pytest.mark.parametrize('method,path,payload',ROUTES)
@pytest.mark.parametrize('exc,category',[
 (ProviderHttpError(SECRET,status_code=429,retry_after=120),'rate_limited'),
 (ProviderHttpError(SECRET,status_code=401),'authentication'),
 (ProviderHttpError(SECRET,status_code=403),'entitlement'),
 (ProviderUnavailableError(SECRET),'authentication'),
 (MissingHistoryError(SECRET),'missing_history'),
 (MarketCacheCorruption(SECRET),'storage'),
 (ValueError(SECRET),'invalid_parameters'),
 (RuntimeError(SECRET),'unknown'),
])
def test_provider_and_execution_errors_are_safe_at_every_data_boundary(method,path,payload,exc,category,caplog):
 class Failing:
  def __getattr__(self,key):
   def fail(*args,**kwargs):raise exc
   return fail
 app=FastAPI()
 for router in (strategy_router,research_router,data_router):app.include_router(router)
 app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=Failing(),market_data=Failing())
 with TestClient(app) as client:response=client.request(method,path,json=payload)
 assert response.status_code>=400 and response.status_code!=422,response.text
 detail=response.json()['detail']
 expected='strategy_execution' if path=='/strategy-lab/backtest' and category=='unknown' else category
 assert detail['category']==expected and detail['message']
 assert not any(s in response.text+caplog.text for s in ('secret-password','private.example','token=unsafe'))
 if category=='rate_limited':
  assert response.status_code==429 and 119<=int(response.headers['retry-after'])<=120
  assert detail['retry_at'] in detail['message']
 else:assert detail['retry_at'] is None and 'retry-after' not in response.headers
 if category=='invalid_parameters':assert response.status_code==400


def test_research_partial_success_does_not_embed_raw_fundamental_error(tmp_path):
 from app.services.research import ResearchService
 from app.storage.database import Database
 from app.storage.symbol_repository import SymbolRepository
 from app.storage.screener_repository import ScreenerRepository
 from app.data.providers.base import Symbol
 from tests.test_research_service import FakeScreener
 db=Database(tmp_path/'profile.db');db.initialize()
 symbols=SymbolRepository(db);symbols.upsert_many([Symbol('AAA','Example',exchange='NASDAQ',tradable=True,cik='0000000001')],'fixture')
 repo=ScreenerRepository(db)
 class Fundamentals:
  def get(self,*args,**kwargs):raise ProviderHttpError(SECRET,status_code=403)
 result=ResearchService(symbols,repo,FakeScreener(repo),Fundamentals()).profile('AAA')
 assert result['metrics']['price']==42
 assert 'entitlement' in result['availability']['fundamentals']['message']
 assert SECRET not in str(result) and 'secret-password' not in str(result)


def test_unexpected_chart_indicator_failure_preserves_bars_without_exception_leak(monkeypatch):
 import app.api.research as research_api
 from app.indicators import indicator_registry
 class Broken:
  def calculate(self,*args,**kwargs):raise RuntimeError(SECRET)
 monkeypatch.setattr(indicator_registry,'create',lambda key:Broken())
 monkeypatch.setattr(research_api,'research_bars',lambda *args:{'bars':[]})
 app=FastAPI();app.include_router(research_router)
 app.dependency_overrides[get_services]=lambda:SimpleNamespace()
 with TestClient(app) as client:
  response=client.post('/research/NQ1!/chart-data',json={'indicators':[{'key':'ema','params':{}}]})
 assert response.status_code==200
 assert response.json()['bars']==[]
 assert response.json()['indicators'][0]['error_category']=='indicator_execution'
 assert 'secret-password' not in response.text
