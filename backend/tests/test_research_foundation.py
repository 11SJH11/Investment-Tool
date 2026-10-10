from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.research_agent import router
from app.research_agent.repository import ResearchRepository
from app.research_agent.analysis import compare, analyze
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.backtesting.strategies import strategy_registry

@pytest.fixture
def setup(tmp_path):
    db=Database(tmp_path/'db');db.initialize()
    return db,ResearchRepository(db),strategy_registry.specs()[0].key

def dataset(start,end,state='DEVELOPMENT'):
    return dict(start=start,end=end,state=state,symbols=['QQQ'],timeframe='1m')

def saved(db,key,day,stamp='10:00',pnl=1):
    trade={'symbol':'QQQ','direction':'long','entry_time':day+'T'+stamp+':00Z','exit_time':day+'T12:00:00Z','net_pnl':pnl,'r_multiple':pnl,'exit_reason':'target'}
    return BacktestRunRepository(db).create(config={'strategy_key':key,'symbols':['QQQ'],'start_date':day,'end_date':day,'primary_timeframe':'1m','market_data_fingerprint':'fixture'},result={'trades':[trade],'metrics':{},'strategy':{'key':key,'implementation':{'sha':'fixture'}}})

def test_firewall_approval_is_permanent_and_restart_preserves_audit(setup):
    db,repo,key=setup
    project=repo.create('Research',key,[dataset('2024-01-01','2024-12-31'),dataset('2025-01-01','2025-12-31','LOCKED_HOLDOUT')])
    base=saved(db,key,'2024-02-01');held=saved(db,key,'2025-02-01')
    repo.inspect_run(project['id'],base['id'])
    with pytest.raises(ValueError,match='Holdout firewall'):repo.inspect_run(project['id'],held['id'])
    holdout=project['datasets'][1]['id']
    with pytest.raises(ValueError):repo.approve_holdout(project['id'],holdout,'yes')
    repo.approve_holdout(project['id'],holdout,'This dataset will no longer be unseen')
    repo.inspect_run(project['id'],held['id'])
    restarted=ResearchRepository(db).get(project['id'])
    assert restarted['datasets'][1]['state']=='INSPECTED_VALIDATION'
    assert restarted['research_debt']['uses']==2 and restarted['baseline_run_id']==base['id']
    with pytest.raises(ValueError):repo.create('Relabel',key,[dataset('2025-01-01','2025-12-31','LOCKED_HOLDOUT')])

def test_already_backtested_period_cannot_be_unseen(setup):
    db,repo,key=setup;saved(db,key,'2024-02-01')
    with pytest.raises(ValueError,match='already covers'):repo.create('False holdout',key,[dataset('2024-01-01','2024-12-31','LOCKED_HOLDOUT')])

def test_cross_project_overlap_and_pause_archive(setup):
    db,repo,key=setup
    project=repo.create('One',key,[dataset('2024-01-01','2024-12-31'),dataset('2025-01-01','2025-12-31','LOCKED_HOLDOUT')])
    with pytest.raises(ValueError):repo.create('Two',key,[dataset('2025-02-01','2025-02-02')])
    run=saved(db,key,'2024-02-01');repo.transition(project['id'],'PAUSED')
    with pytest.raises(ValueError):repo.inspect_run(project['id'],run['id'])
    repo.transition(project['id'],'BASELINE_ANALYSIS');repo.inspect_run(project['id'],run['id'])
    repo.transition(project['id'],'ARCHIVED')
    with pytest.raises(ValueError):repo.transition(project['id'],'BASELINE_ANALYSIS')
    with pytest.raises(ValueError):repo.approve_holdout(project['id'],project['datasets'][1]['id'],'This dataset will no longer be unseen')

def test_winner_removal_replacement_and_fingerprint_are_deterministic(setup):
    db,_,key=setup
    a=saved(db,key,'2024-02-01',pnl=-1);b=saved(db,key,'2024-02-01',stamp='11:00',pnl=3)
    result=compare(a,b)
    assert result['removed_losers']['n']==1 and result['removed']['total_r']==-1
    assert result['introduced']['n']==1 and result['introduced']['total_r']==3
    assert result['data_equivalent'] and not result['control_parity']
    assert compare(a,a)['control_parity']
    b['config']['market_data_fingerprint']='changed'
    assert not compare(a,b)['data_equivalent']
    b['result']['trades'].append(dict(b['result']['trades'][0]))
    with pytest.raises(ValueError,match='Ambiguous'):compare(a,b)
    a['config'].pop('market_data_fingerprint')
    assert analyze(a)['data_fingerprint'] is None

def test_api_rejects_unsupported_actions_and_requires_explicit_ack(setup):
    db,repo,key=setup;app=FastAPI();app.state.services=SimpleNamespace(database=db);app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        path='/api/strategy-lab/research-agent'
        p=client.post(path,json={'name':'Project','strategy_key':key,'datasets':[dataset('2024-01-01','2024-12-31')]}).json()
        assert p['mode']=='READ_ONLY'
        assert client.post(path+'/'+p['id']+'/state',json={'state':'RUN_ARBITRARY_CODE'}).status_code==422
        assert client.get(path+'/'+p['id']).json()['state']=='CREATED'


def test_actual_market_requests_guard_warmup_cache_and_provider_changes(setup,tmp_path):
    from app.research_agent.access import scope, ResearchAccessError
    from tests.test_mt5_market_data import provider,Terminal,START,END
    from app.services.market_data import MarketDataService
    from app.storage.market_cache_repository import MarketCacheRepository
    from app.storage.market_store import MarketStore
    db,repo,key=setup
    dev=dataset('2025-01-02','2025-01-02');dev['symbols']=['NQ1!']
    held=dataset('2025-01-03','2025-01-03','LOCKED_HOLDOUT');held['symbols']=['NQ1!']
    project=repo.create('Scoped',key,[dev,held]);terminal=Terminal();p=provider(terminal)
    market=MarketDataService(p,MarketStore(tmp_path/'bars'),MarketCacheRepository(db))
    with scope(db,project['id']):
        market.get_bars('NQH25','1m',START,END)
        market.get_bars('NQH25','1m',START,END)
        assert len(terminal.calls)==1
        from datetime import timedelta
        with pytest.raises(ResearchAccessError,match='Holdout'):market.get_bars('NQH25','1m',START+timedelta(days=1),END+timedelta(days=1))
        with pytest.raises(ResearchAccessError,match='warmup'):market.get_bars('NQH25','1m',START-timedelta(days=1),END)
        p.cache_namespace+='changed'
        with pytest.raises(ResearchAccessError,match='namespace'):market.get_bars('NQH25','1m',START,END)
    assert len(terminal.calls)==1
    repo.approve_holdout(project['id'],project['datasets'][1]['id'],'This dataset will no longer be unseen')
    with scope(db,project['id']):
        with pytest.raises(ResearchAccessError):market.get_bars('NQH25','1m',START+timedelta(days=1),END+timedelta(days=1))

def test_baseline_submission_is_idempotent_and_payload_is_frozen(setup):
    from app.research_agent.workflow import start,validate_submission
    from app.api.strategy_lab import BacktestRequest
    db,repo,key=setup
    project=repo.create('Queued',key,[dataset('2024-01-01','2024-12-31')])
    class Jobs:
        def __init__(self):self.items={}
        def enqueue(self,payloads,request_key):
            self.items.setdefault(request_key,{'id':request_key,'status':'queued','payload':payloads[0]})
            return [self.items[request_key]]
        def get(self,id):return self.items[id]
    jobs=Jobs();services=SimpleNamespace(database=db,backtest_jobs=jobs)
    payload=BacktestRequest(strategy_key=key,symbols=['QQQ'],start_date='2024-02-01',end_date='2024-02-02',primary_timeframe='1m').model_dump()
    first=start(services,project['id'],payload);second=start(services,project['id'],payload)
    assert first['baseline_job_id']==second['baseline_job_id'] and len(jobs.items)==1
    approved=first['baseline_payload'];validate_submission(db,approved)
    with pytest.raises(ValueError):validate_submission(db,{**approved,'risk_value':999})
    with pytest.raises(ValueError):start(services,project['id'],{**payload,'risk_value':999})
    assert ResearchRepository(db).get(project['id'])['baseline_payload']==approved


def test_pause_before_submission_resumes_to_created(setup):
    _,repo,key=setup
    project=repo.create('Before run',key,[dataset('2024-01-01','2024-12-31')])
    repo.transition(project['id'],'PAUSED')
    assert repo.transition(project['id'],'BASELINE_ANALYSIS')['state']=='CREATED'


def test_real_queue_engine_save_observation_and_restart(setup,monkeypatch):
    from dataclasses import replace
    import pandas as pd
    from app.services.backtest import BacktestService
    from app.services.backtest_jobs import BacktestJobs
    from app.research_agent.workflow import start,observe,validate_submission
    from app.research_agent.access import check
    from app.api.strategy_lab import BacktestRequest
    from tests.test_backtest_jobs import wait_for
    from tests.test_market_concepts import bars
    from tests.test_phase52_saved_runs_and_chart_series import HoldToEnd
    db,repo,_=setup
    class Strategy(HoldToEnd):
        spec=replace(HoldToEnd.spec,key='research_queue_fixture')
    monkeypatch.setitem(strategy_registry._items,Strategy.spec.key,Strategy)
    class FixtureService(BacktestService):
        def prepare(self,payload,**kwargs):
            validate_submission(db,payload)
            begin=pd.Timestamp('2026-01-02T14:30Z');end=pd.Timestamp('2026-01-02T14:37Z')
            check('QQQ','1m',begin,end,'fixture')
            return dict(strategy_key=Strategy.spec.key,symbols=['QQQ'],primary='1m',additional=[],session='regular',requested_session='regular',
                start=begin,end=end,delay=0,frames_by_symbol={'QQQ':{'1m':bars()}},diagnostic_history={},diagnostic_warnings=[],providers={'QQQ':'fixture'},source_namespaces={'QQQ':'fixture'})
    service=FixtureService(None,BacktestRunRepository(db));jobs=BacktestJobs(db,service,1)
    services=SimpleNamespace(database=db,backtest_jobs=jobs)
    project=repo.create('Real engine',Strategy.spec.key,[dataset('2026-01-01','2026-01-03')])
    payload=BacktestRequest(strategy_key=Strategy.spec.key,symbols=['QQQ'],start_date='2026-01-02',end_date='2026-01-02',primary_timeframe='1m').model_dump()
    try:
        submitted=start(services,project['id'],payload);job_id=submitted['baseline_job_id']
        wait_for(lambda:jobs.get(job_id)['status'] in {'completed','failed'})
        assert jobs.get(job_id)['status']=='completed',jobs.get(job_id)
        result=observe(services,project['id'])
        assert result['state']=='BASELINE_ANALYSIS'
        run_id=result['baseline_run_id'];snapshot=service.runs.get(run_id)
        assert snapshot['result']['trades']
        assert result['analyses'][str(run_id)]['data_fingerprint']
        assert any(e['action']=='market_data' for e in result['events'])
        assert observe(services,project['id'])==result
        assert ResearchRepository(db).get(project['id'])==result
        assert service.runs.get(run_id)==snapshot and len(service.runs.list())==1
    finally:jobs.close()


def test_cancelled_baseline_resume_reuses_config_not_cancelled_job(setup):
    from app.research_agent.workflow import start
    from app.api.strategy_lab import BacktestRequest
    db,repo,key=setup
    class Jobs:
        def __init__(self):self.items={}
        def enqueue(self,payloads,request_key):
            self.items.setdefault(request_key,dict(id=request_key,status='queued',payload=payloads[0]))
            return [self.items[request_key]]
        def get(self,id):
            if id not in self.items:raise ValueError('Job not found')
            return self.items[id]
        def cancel(self,id):self.items[id]['status']='cancelled'
    jobs=Jobs();services=SimpleNamespace(database=db,backtest_jobs=jobs)
    project=repo.create('Recover',key,[dataset('2024-01-01','2024-12-31')]);id=project['id']
    payload=BacktestRequest(strategy_key=key,symbols=['QQQ'],start_date='2024-02-01',end_date='2024-02-02',primary_timeframe='1m').model_dump()
    first=start(services,id,payload)
    unrelated=saved(db,key,'2024-02-01')
    with pytest.raises(ValueError,match='frozen baseline'):repo.inspect_run(id,unrelated['id'])
    app=FastAPI();app.state.services=services;app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        path='/api/strategy-lab/research-agent/'+id+'/state'
        assert client.post(path,json={'state':'PAUSED'}).status_code==200
        resumed=client.post(path,json={'state':'BASELINE_ANALYSIS'}).json()
        assert resumed['baseline_job_id']!=first['baseline_job_id']
        assert resumed['baseline_payload']==first['baseline_payload'] and len(jobs.items)==2
        assert client.post(path,json={'state':'PAUSED'}).status_code==200
        del jobs.items[resumed['baseline_job_id']]
        assert client.post(path,json={'state':'BASELINE_ANALYSIS'}).status_code==200
