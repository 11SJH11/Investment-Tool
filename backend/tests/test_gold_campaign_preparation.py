from types import SimpleNamespace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.research_agent.discovery import prepare, queue, required_timeframes
from app.research_agent.campaign_projects import provision
from app.research_agent.repository import ResearchRepository
from app.research_agent.access import scope, check, ResearchAccessError
from app.storage.market_store import MarketStore
from tests.test_research_campaigns import repo
from tests.test_campaign_launch import launchable
from app.research_agent.launch import launch
from tests.test_campaign_preparation import setup, tick

KEY='gold_asia_15m_ifvg_research_v1'


def gold_request(key='gold'):
    return dict(request_key=key,mode='IMPROVE_STRATEGY',strategy_key=KEY,
        policy=dict(symbols=['XAUUSD'],timeframes=['1m'],dataset=dict(
            warmup_sessions=1,min_development_sessions=2,min_holdout_sessions=1,internal_windows=2)))


def gold_cache(tmp_path, *, missing=False, incomplete=False):
    store=MarketStore(tmp_path/'gold')
    # Includes Sunday 20:00 ET on both sides of DST, without inventing weekdays.
    stamps=pd.to_datetime(['2026-03-02T01:00Z','2026-03-03T01:00Z',
                          '2026-03-09T00:00Z','2026-03-10T00:00Z'])
    for tf in ['1m','15m']:
        if missing and tf=='15m':continue
        times=stamps[:-1] if incomplete and tf=='15m' else stamps
        store.write_bars('gold-fixture','XAUUSD',tf,pd.DataFrame(dict(
            timestamp=times,open=3000,high=3001,low=2999,close=3000,volume=1)))
    return SimpleNamespace(store=store,provider_for=lambda s:SimpleNamespace(cache_namespace='gold-fixture'))


def test_gold_dependencies_share_one_project_dates_and_provider_firewall(repo,tmp_path):
    campaign=repo.create(gold_request())
    entries=queue(campaign['request'])
    assert required_timeframes(entries,['1m'])==['1m','15m']
    services=SimpleNamespace(database=repo.database,market_data=gold_cache(tmp_path))
    prepared=prepare(services,campaign['id'])
    assert list(prepared['plans'])==['XAUUSD:1m']
    plan=prepared['plans']['XAUUSD:1m']
    assert plan['warmup']['start']=='2026-03-01'
    assert plan['development']['end']=='2026-03-08'
    assert set(plan['coverage']['input_fingerprints'])=={'1m','15m'}
    links=provision(repo.database,campaign['id'])
    assert len(links)==1
    project=ResearchRepository(repo.database).get(links[0]['project_id'])
    assert project['provider_bindings']=={'XAUUSD:1m':'gold-fixture','XAUUSD:15m':'gold-fixture'}
    def bounds(day):
        start=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('America/New_York'))
        return start,start+timedelta(days=1)
    with scope(repo.database,project['id']):
        check('XAUUSD','15m',*bounds(plan['development']['start']),namespace='gold-fixture')
        with pytest.raises(ResearchAccessError,match='namespace changed'):
            check('XAUUSD','15m',*bounds(plan['development']['start']),namespace='other-feed')
        with pytest.raises(ResearchAccessError,match='Holdout firewall'):
            check('XAUUSD','15m',*bounds(plan['holdout']['start']),namespace='gold-fixture')


@pytest.mark.parametrize('options',[{'missing':True},{'incomplete':True}])
def test_missing_dependency_does_not_move_dates_or_prepare(repo,tmp_path,options):
    campaign=repo.create(gold_request())
    services=SimpleNamespace(database=repo.database,market_data=gold_cache(tmp_path,**options))
    with pytest.raises(ValueError):prepare(services,campaign['id'])
    assert repo.get(campaign['id'])['status']=='DRAFT'


def test_gold_launch_defaults_to_auto_without_docker_or_model(launchable):
    services,request,_=launchable
    request['campaign']=gold_request()
    result=launch(services,request)
    assert result['launch']['configuration']['engine']['session']=='auto'


@pytest.mark.parametrize('session',['regular','extended'])
def test_equity_session_cannot_silently_exclude_asia(launchable,session):
    services,request,_=launchable
    request['campaign']=gold_request();request['engine']['session']=session
    with pytest.raises(ValueError,match='Spot-metal'):launch(services,request)
    assert services.research_director.campaigns.list()==[]


def test_provider_preparation_fetches_both_inputs_before_provisioning(setup):
    from app.research_agent.preparation import start
    services,repo,_,provider=setup
    campaign=repo.create(gold_request())
    authorized=start(services,campaign['id'],30)
    assert authorized['preparation']['timeframes']==['1m','15m']
    for _ in range(3):tick(setup)
    done=repo.get(campaign['id'])
    assert done['status']=='PREPARED',done
    assert {tf for _,tf,_,_ in provider.calls}=={'1m','15m'}
    assert len(provision(repo.database,campaign['id']))==1


def test_preparation_error_does_not_expose_exception_secrets():
    from app.research_agent.preparation_errors import preparation_failure
    for error in [RuntimeError('token=private-secret'),ValueError('Required private-secret')]:
        detail=preparation_failure(error)
        assert 'private-secret' not in str(detail)
        assert detail['category'] and detail['message']


def test_missing_dependency_launch_has_actionable_failure(launchable,tmp_path):
    services,request,backtest=launchable
    services.market_data=gold_cache(tmp_path,missing=True)
    request['campaign']=gold_request()
    item=launch(services,request)
    services.research_director.tick()
    failed=services.research_director.campaigns.get(item['id'])
    assert failed['status']=='PREPARATION_FAILED'
    assert failed['last_error_detail']['category']=='required_history_missing'
    assert not backtest.calls


def test_gold_campaign_runs_real_engine_on_synthetic_cache_without_model_or_docker(repo,tmp_path):
    from tests.test_gold_ifvg_acceptance import fixture
    from tests.test_research_director import advance_until
    from app.services.market_data import MarketDataService
    from app.services.backtest import BacktestService
    from app.services.backtest_jobs import BacktestJobs
    from app.storage.market_cache_repository import MarketCacheRepository
    from app.storage.backtest_run_repository import BacktestRunRepository
    from app.research_agent.director import ResearchDirector
    from app.research_agent.launch import CONSENT
    sessions=[fixture(day) for day in ['2026-03-01','2026-03-02','2026-03-08','2026-03-09']]
    frames={tf:pd.concat([s[tf] for s in sessions],ignore_index=True) for tf in ['1m','15m']}
    class Provider:
        key='fixture';cache_namespace='gold-fixture'
        def get_bars(self,symbol,timeframe,start,end):
            f=frames[timeframe]
            return f[(f.timestamp>=start)&(f.timestamp<end)].copy()
    store=MarketStore(tmp_path/'engine-cache')
    for tf,f in frames.items():store.write_bars('gold-fixture','XAUUSD',tf,f)
    market=MarketDataService(Provider(),store,MarketCacheRepository(repo.database))
    runs=BacktestRunRepository(repo.database)
    jobs=BacktestJobs(repo.database,BacktestService(market,runs),1)
    services=SimpleNamespace(database=repo.database,market_data=market,backtest_jobs=jobs)
    director=ResearchDirector(services,start_thread=False);services.research_director=director
    try:
        campaign=launch(services,dict(campaign=gold_request(),engine=dict(
            starting_balance=10000,risk_value=1,commission_per_order=0,spread_bps=0,slippage_bps=0,max_leverage=1),consent=CONSENT))
        advance_until(director,campaign['id'],'BASELINES_COMPLETE')
        done=director.campaigns.get(campaign['id'])
        project=ResearchRepository(repo.database).get(done['projects'][0]['project_id'])
        result=runs.get(project['baseline_run_id'])
        assert result['config']['session']=='auto'
        assert 6 in result['config']['trading_weekdays']
        assert len(result['result']['trades'])==2
        # Sparse multi-session history also creates a boundary FVG: the frozen
        # strategy takes that first inversion, rather than choosing the later win.
        assert [t['r_multiple'] for t in result['result']['trades']]==[1,-1]
        assert done['plans']['XAUUSD:1m']['holdout']['start']=='2026-03-09'
        assert all(t['metadata']['asia_session_key']<'2026-03-09' for t in result['result']['trades'])
    finally:
        director.close();jobs.close()
