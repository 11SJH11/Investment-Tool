from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.http import ProviderHttpError
from app.research_agent.campaign_policy import CampaignPolicy, DatasetPolicy
from app.research_agent.campaigns import Campaigns
from app.research_agent.campaign_projects import provision
from app.research_agent.director import ResearchDirector
from app.research_agent.preparation import start
from app.research_agent.repository import ResearchRepository
from app.services.market_data import MarketDataService
from app.services.market_warmup import MarketWarmupManager
from app.storage.database import Database
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository
from tests.test_market_warmup import HeldExecutor


class Provider:
    key='fixture'
    cache_namespace='fixture-equities'
    def __init__(self):self.calls=[];self.error=None;self.after=None
    def get_bars(self,symbol,timeframe,start,end):
        self.calls.append((symbol,timeframe,start,end))
        if self.error:raise self.error
        stamps=pd.date_range(pd.Timestamp(start).normalize(),pd.Timestamp(end),freq='B')+pd.Timedelta(hours=14)
        stamps=stamps[(stamps>=start)&(stamps<end)]
        if self.after:self.after()
        return pd.DataFrame(dict(timestamp=stamps,open=1,high=2,low=1,close=2,volume=10))


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr('app.services.market_warmup.ThreadPoolExecutor',HeldExecutor)
    database=Database(tmp_path/'research.db');database.initialize()
    provider=Provider()
    market=MarketDataService(provider,MarketStore(tmp_path/'cache'),MarketCacheRepository(database))
    warmer=MarketWarmupManager(market,database)
    services=SimpleNamespace(database=database,market_data=market,market_warmup=warmer,backtest_jobs=None)
    services.research_director=ResearchDirector(services,start_thread=False)
    policy=CampaignPolicy(dataset=DatasetPolicy(warmup_sessions=1,min_development_sessions=2,min_holdout_sessions=1,internal_windows=2))
    repo=Campaigns(database)
    campaign=repo.create(dict(request_key='history',mode='FIND_STRATEGIES',policy=policy.model_dump()))
    yield services,repo,campaign,provider
    services.research_director.close();services.market_warmup.close()


def tick(setup):
    services,_,_,_=setup
    services.research_director.tick()
    services.market_warmup.executor.run()
    services.research_director.tick()


def test_provider_history_completes_without_browser_and_freezes_dates(setup):
    services,repo,campaign,provider=setup
    approved=start(services,campaign['id'],30)
    assert not provider.calls
    assert start(services,campaign['id'],30)==approved
    tick(setup)
    done=repo.get(campaign['id'])
    assert done['status']=='PREPARED',done
    assert done['discovery']['version']=='provider_cache_discovery_v1'
    assert len(services.market_warmup.list())==1
    begin=datetime.fromisoformat(approved['preparation']['start'])
    end=datetime.fromisoformat(approved['preparation']['end'])
    assert all(begin<=a<b<=end and b-a<=timedelta(days=7) for _,_,a,b in provider.calls)
    assert done['deadline']==approved['deadline']
    assert done['preparation']['status']=='COMPLETED'
    assert start(services,campaign['id'],30)==done
    with pytest.raises(ValueError,match='immutable'):start(services,campaign['id'],40)
    links=provision(services.database,campaign['id'])
    assert ResearchRepository(services.database).get(links[0]['project_id'])['provider_bindings']=={'QQQ:1m':'fixture-equities'}


def test_restart_reuses_job_and_does_not_duplicate_completed_chunks(setup):
    services,repo,campaign,provider=setup
    start(services,campaign['id'],30)
    services.research_director.tick()
    job=services.market_warmup.list()[0]
    provider.after=lambda:services.market_warmup.pause(job['id'])
    services.market_warmup.executor.run()
    assert len(provider.calls)==1
    services.research_director.close();services.market_warmup.close()
    services.market_warmup=MarketWarmupManager(services.market_data,services.database)
    services.research_director=ResearchDirector(services,start_thread=False)
    provider.after=None
    tick(setup)
    assert repo.get(campaign['id'])['status']=='PREPARED'
    assert len(provider.calls)==len(set(provider.calls))==5
    assert services.market_warmup.list()[0]['id']==job['id']


@pytest.mark.parametrize('action',['pause','cancel'])
def test_campaign_control_stops_download_and_settings_cannot_bypass_it(setup,action):
    services,repo,campaign,provider=setup
    approved=start(services,campaign['id'],30)
    services.research_director.tick()
    job=services.market_warmup.list()[0]
    services.research_director.control(campaign['id'],action)
    services.market_warmup.executor.run()
    services.market_warmup.resume(job['id'])
    services.market_warmup.executor.run()
    assert not provider.calls
    assert repo.get(campaign['id'])['status']==('PAUSED' if action=='pause' else 'CANCELLED')
    if action=='pause':
        services.research_director.control(campaign['id'],'resume')
        # User pause revoked the first attempt; the failed unauthorized Settings
        # resume is not silently retried as a provider outage.
        assert repo.get(campaign['id'])['deadline']==approved['deadline']


def test_existing_holdout_blocks_all_provider_calls(setup):
    services,repo,campaign,provider=setup
    item=start(services,campaign['id'],30)
    key=item['preparation']['entries'][0]['strategy_key']
    ResearchRepository(services.database).create('Protected',key,[dict(symbols=['QQQ'],timeframe='1m',
        start=item['preparation']['start_date'],end=item['preparation']['end_date'],state='LOCKED_HOLDOUT')])
    tick(setup)
    assert not provider.calls
    assert repo.get(campaign['id'])['status']=='PAUSED'


def test_provider_switch_and_expired_preparation_are_rejected(setup):
    services,repo,campaign,provider=setup
    start(services,campaign['id'],30)
    services.research_director.tick()
    provider.cache_namespace='other-provider'
    services.market_warmup.executor.run()
    assert not provider.calls
    services.research_director.tick()
    assert repo.get(campaign['id'])['status']=='PAUSED'
    with services.database.connect() as c:
        item=repo._get(c,campaign['id'])
        item['preparation']['deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        repo._save(c,item)
    with pytest.raises(ValueError,match='deadline'):services.research_director.control(campaign['id'],'resume')


def test_429_respects_cooldown_without_exposing_secrets(setup):
    services,repo,campaign,provider=setup
    provider.error=ProviderHttpError('private key and URL',status_code=429,retry_after=3600)
    start(services,campaign['id'],30)
    tick(setup)
    for _ in range(4):tick(setup)
    assert len(provider.calls)==1
    job=services.market_warmup.list()[0]
    assert job['error_category']=='rate_limited' and job['retry_at']
    assert 'private key' not in str(job)
    assert repo.get(campaign['id'])['status']=='PREPARING'


def test_nonoverlapping_manual_cache_does_not_expand_authorized_bounds(setup):
    services,repo,campaign,provider=setup
    item=start(services,campaign['id'],30)
    end=datetime.fromisoformat(item['preparation']['end'])
    bars=provider.get_bars('QQQ','1m',end+timedelta(days=20),end+timedelta(days=23))
    services.market_data.store.write_bars(provider.cache_namespace,'QQQ','1m',bars)
    services.market_data.coverage.extend(provider.cache_namespace,'QQQ','1m',end+timedelta(days=20),end+timedelta(days=23))
    provider.calls.clear()
    tick(setup)
    # The shared service would bridge a disjoint future cache interval. Its
    # low-level request gate must reject that expansion before provider access.
    assert repo.get(campaign['id'])['status']=='PAUSED'
    assert not provider.calls


def test_original_wall_deadline_and_remaining_compute_survive_baseline_start(setup):
    services,repo,campaign,_=setup
    approved=start(services,campaign['id'],30)
    tick(setup)
    links=provision(services.database,campaign['id'])
    configs={p['project_id']:dict(starting_balance=10000,risk_value=1,commission_per_order=1,
        spread_bps=1,slippage_bps=1,max_leverage=1) for p in links}
    active=services.research_director.start_baselines(campaign['id'],configs)
    assert active['deadline']==approved['deadline'] and active['started_at']==approved['started_at']
    assert active['reserved']['compute_minutes']<=active['request']['policy']['budget']['compute_minutes']


def test_stop_after_current_keeps_completed_chunk_then_resumes(setup):
    services,repo,campaign,provider=setup
    start(services,campaign['id'],30)
    services.research_director.tick()
    provider.after=lambda:services.research_director.control(campaign['id'],'stop_after_current')
    services.market_warmup.executor.run()
    assert len(provider.calls)==1
    assert repo.get(campaign['id'])['status']=='PAUSED'
    provider.after=None
    services.research_director.control(campaign['id'],'resume')
    tick(setup)
    assert repo.get(campaign['id'])['status']=='PREPARED'
    assert len(provider.calls)==len(set(provider.calls))==5


def test_new_holdout_between_chunks_revokes_remaining_downloads(setup):
    services,repo,campaign,provider=setup
    item=start(services,campaign['id'],30)
    services.research_director.tick()
    def protect():
        provider.after=None
        ResearchRepository(services.database).create('Protected',item['preparation']['entries'][0]['strategy_key'],[
            dict(symbols=['QQQ'],timeframe='1m',start=item['preparation']['start_date'],
                 end=item['preparation']['end_date'],state='LOCKED_HOLDOUT')])
    provider.after=protect
    services.market_warmup.executor.run()
    services.research_director.tick()
    assert len(provider.calls)==1
    assert repo.get(campaign['id'])['status']=='PAUSED'


def test_transient_failure_backoff_and_retry_limit_are_durable(setup):
    services,repo,campaign,provider=setup
    provider.error=ProviderHttpError('private',status_code=503)
    start(services,campaign['id'],30)
    tick(setup)
    for _ in range(5):tick(setup)
    assert len(provider.calls)==1
    for attempt in range(3):
        with services.database.connect() as c:
            item=repo._get(c,campaign['id'])
            item['preparation']['retry_not_before']['1m']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
            repo._save(c,item)
        tick(setup)
    assert len(provider.calls)==4
    assert repo.get(campaign['id'])['status']=='PAUSED'
    assert repo.get(campaign['id'])['preparation']['retries']['1m']==3


def test_history_authorization_api_requires_acknowledgement(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_services
    from app.api.research_campaigns import router
    services,repo,campaign,provider=setup
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:services
    with TestClient(app) as client:
        path='/strategy-lab/research-campaigns/'+campaign['id']+'/prepare-history'
        assert client.post(path,json={'lookback_days':30}).status_code==422
        response=client.post(path,json=dict(lookback_days=30,
            acknowledgement='Fetch bounded historical data using my configured provider; no strategy execution'))
        assert response.status_code==200,response.text
        assert response.json()['status']=='PREPARING'
    assert not provider.calls
