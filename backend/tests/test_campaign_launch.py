from copy import deepcopy
from types import SimpleNamespace

import pandas as pd
import pytest

from tests.test_research_campaigns import repo
from tests.test_research_discovery import market
from tests.test_research_director import Backtest, advance_until
from app.research_agent.director import ResearchDirector
from app.research_agent.launch import launch, CONSENT
from app.services.backtest_jobs import BacktestJobs


def test_structural_worker_failure_rejects_launch_before_persistence(launchable):
    from unittest.mock import Mock
    from app.research_agent.sandbox import SandboxError
    services,request,backtest=launchable
    request.update(structural=True)
    request['campaign']['policy']={'send_development_summaries':True,'code_generation':True}
    services.research_loop=SimpleNamespace(committee=SimpleNamespace(model=SimpleNamespace(status=lambda:dict(configured=True,pricing=True))))
    services.research_author=object()
    probe=Mock(side_effect=SandboxError('DOCKER_DAEMON_UNAVAILABLE'))
    services.research_sandbox=SimpleNamespace(docker=SimpleNamespace(preflight=probe))
    with pytest.raises(SandboxError,match='DOCKER_DAEMON_UNAVAILABLE'):
        launch(services,request)
    probe.assert_called_once()
    assert not services.research_director.campaigns.list() and not backtest.calls


@pytest.fixture
def launchable(repo,tmp_path):
    backtest=Backtest(repo.database)
    jobs=BacktestJobs(repo.database,backtest,1)
    services=SimpleNamespace(database=repo.database,backtest_jobs=jobs,
        market_data=market(tmp_path,pd.date_range('2020-01-01T15:00Z',periods=800,freq='B')))
    director=ResearchDirector(services,start_thread=False)
    services.research_director=director
    request=dict(campaign=dict(request_key='launch',mode='FIND_STRATEGIES'),
        engine=dict(starting_balance=10000,risk_value=1,commission_per_order=0,spread_bps=1,slippage_bps=1,max_leverage=1,sizing_mode='risk_pct'),consent=CONSENT)
    yield services,request,backtest
    director.close();jobs.close()


def test_single_launch_prepares_and_runs_without_further_browser_calls(launchable):
    services,request,backtest=launchable
    item=launch(services,request)
    assert not backtest.calls
    assert launch(services,request)['id']==item['id']
    advance_until(services.research_director,item['id'],'BASELINES_COMPLETE')
    result=services.research_director.campaigns.report(item['id'])
    assert result['summary']['baseline_runs_completed']>0
    assert all(f['verdict']=='DEVELOPMENT_ONLY' for f in result['morning_report']['families'])
    assert not result['summary']['holdout_consumed_by_campaign']
    count=len(backtest.calls)
    launch(services,request);services.research_director.tick()
    assert len(backtest.calls)==count


def test_launch_configuration_cannot_change_on_retry(launchable):
    services,request,_=launchable
    item=launch(services,request)
    altered=deepcopy(request);altered['engine']['risk_value']=2
    with pytest.raises(ValueError,match='immutable'):launch(services,altered)
    assert services.research_director.campaigns.get(item['id'])['launch']['configuration']['engine']['risk_value']==1


@pytest.mark.parametrize('change',[{'risk_mode':'percent'},{'starting_balance':0},{'risk_value':True},{'slippage_bps':float('nan')},{'start_date':'2020-01-01'},{'sizing_mode':'quantity'}])
def test_launch_rejects_invalid_engine_contract_before_campaign_creation(launchable,change):
    services,request,backtest=launchable
    request['engine'].update(change)
    with pytest.raises(ValueError):launch(services,request)
    assert not services.research_director.campaigns.list() and not backtest.calls


def test_missing_cache_fails_once_without_provider_fallback_or_queue(launchable):
    services,request,backtest=launchable
    services.market_data=None
    item=launch(services,request)
    services.research_director.tick()
    assert services.research_director.campaigns.get(item['id'])['status']=='PREPARATION_FAILED'
    services.research_director.tick()
    assert not backtest.calls


def test_campaign_launch_api_requires_explicit_authority(launchable):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_campaigns import router
    services,request,_=launchable
    app=FastAPI();app.include_router(router);app.state.services=services
    with TestClient(app) as client:
        assert client.post('/strategy-lab/research-campaigns/launch',json={}).status_code==422
        response=client.post('/strategy-lab/research-campaigns/launch',json=request)
        assert response.status_code==200,response.text
        assert response.json()['status']=='DRAFT'
        assert client.get('/strategy-lab/research-campaigns/'+response.json()['id']).json()['morning_report']['families']==[]
