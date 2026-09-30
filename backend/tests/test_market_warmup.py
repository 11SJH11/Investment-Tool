from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from time import monotonic, sleep
from types import SimpleNamespace

import pandas as pd
import pytest

from app.data.http import ProviderHttpError
from app.services.market_coordination import ProviderPriorityLock, background_market_work, WarmupPaused
from app.services.market_warmup import MarketWarmupManager, next_chunk
from app.storage.database import Database


class HeldExecutor:
    def __init__(self, **kwargs): self.tasks=[]
    def submit(self, fn, *args): self.tasks.append((fn,args))
    def shutdown(self, **kwargs): pass
    def run(self):
        while self.tasks:
            fn,args=self.tasks.pop(0)
            fn(*args)


class Market:
    def __init__(self): self.covered=None; self.calls=[]; self.after=None; self.error=None
    def latest_available_end(self, symbol, tf, end): return end
    def cached_coverage(self, *args, **kwargs): return self.covered
    def get_bars(self, symbol, tf, start, end, **kwargs):
        self.calls.append((start,end))
        if self.error: raise self.error
        if self.covered: self.covered=(min(start,self.covered[0]),max(end,self.covered[1]))
        else: self.covered=(start,end)
        if self.after: self.after()
        return pd.DataFrame({'close':[100]})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import app.services.market_warmup as module
    monkeypatch.setattr(module, 'ThreadPoolExecutor', HeldExecutor)
    db=Database(tmp_path/'isolated.db'); db.initialize()
    market=Market()
    manager=MarketWarmupManager(market,db)
    yield manager,market,db
    manager.close()


def test_chunks_are_bounded_and_completed_job_is_durable(setup):
    manager,market,db=setup
    job=manager.start(['AAPL'],lookback_days=30)
    manager.executor.run()
    done=manager.get(job['id'])
    assert done['status']=='completed' and done['chunks_completed']==5
    assert all(end-start<=timedelta(days=7) for start,end in market.calls)
    assert all(market.calls[i+1][1]==market.calls[i][0] for i in range(4))
    restarted=MarketWarmupManager(market,db)
    try:
        assert restarted.get(job['id'])==done
        assert not restarted.executor.tasks
    finally: restarted.close()


def test_pause_after_chunk_resume_reuses_progress(setup):
    manager,market,db=setup
    job=manager.start(['AAPL'],lookback_days=20)
    market.after=lambda: manager.pause(job['id'])
    manager.executor.run()
    paused=manager.get(job['id'])
    assert paused['status']=='paused' and paused['chunks_completed']==1
    assert paused['items'][0]['downloaded_coverage']
    manager.close()
    market.after=None
    restarted=MarketWarmupManager(market,db)
    try:
        assert restarted.get(job['id'])['status']=='paused'
        restarted.resume(job['id']); restarted.executor.run()
        assert restarted.get(job['id'])['status']=='completed'
        assert len(market.calls)==3 and len(set(market.calls))==3
    finally: restarted.close()


def test_restart_recovers_running_job_as_paused_without_provider_call(setup):
    manager,market,db=setup
    job=manager.start(['AAPL'])
    document=manager.get(job['id']); document['status']='running'; manager.repository.save(document)
    restarted=MarketWarmupManager(market,db)
    try:
        assert restarted.get(job['id'])['status']=='paused'
        assert not market.calls and not restarted.executor.tasks
    finally: restarted.close()


def test_existing_coverage_extends_adjacent_not_across_large_gap(setup):
    manager,market,_=setup
    job=manager.start(['AAPL'],lookback_days=90)
    end=datetime.fromisoformat(job['items'][0]['requested_end'])
    market.covered=(end-timedelta(days=3),end)
    manager.executor.run()
    assert market.calls[0]==(end-timedelta(days=10),end-timedelta(days=3))
    assert all(b-a<=timedelta(days=7) for a,b in market.calls)
    assert manager.get(job['id'])['status']=='completed'


def test_fully_cached_job_makes_zero_bar_requests(setup):
    manager,market,_=setup
    job=manager.start(['AAPL'])
    item=job['items'][0]
    market.covered=tuple(datetime.fromisoformat(item[k]) for k in ('requested_start','requested_end'))
    manager.executor.run()
    assert not market.calls
    assert manager.get(job['id'])['status']=='completed'


def test_rate_limit_preserves_chunk_and_enforces_retry_without_exposing_error(setup):
    manager,market,_=setup
    job=manager.start(['AAPL'],lookback_days=20)
    market.after=lambda: setattr(market,'error',ProviderHttpError('secret-token private-url',status_code=429,retry_after=3600))
    manager.executor.run()
    failed=manager.get(job['id'])
    assert failed['status']=='failed' and failed['chunks_completed']==1
    assert failed['error_category']=='rate_limited' and failed['retry_at']
    assert 'secret-token' not in str(failed) and 'private-url' not in str(failed)
    with pytest.raises(ValueError,match='cooldown'): manager.resume(job['id'])
    assert len(market.calls)==2


def test_failed_chunk_is_retried_but_successful_chunk_is_not(setup):
    manager,market,_=setup
    job=manager.start(['AAPL'],lookback_days=15)
    market.after=lambda: setattr(market,'error',RuntimeError('secret'))
    manager.executor.run()
    first,failed=market.calls
    market.after=None; market.error=None
    manager.resume(job['id']); manager.executor.run()
    assert market.calls.count(first)==1 and market.calls.count(failed)==2
    assert manager.get(job['id'])['status']=='completed'


def test_duplicate_active_job_and_caller_mutation_isolation(setup):
    manager,market,_=setup
    job=manager.start(['aapl','AAPL'])
    assert manager.start(['AAPL'])['id']==job['id']
    job['items'][0]['symbol']='mutated'
    assert manager.get(job['id'])['items'][0]['symbol']=='AAPL'
    manager.pause(job['id']); manager.executor.run()
    assert not market.calls and manager.get(job['id'])['status']=='paused'


def wait_for(predicate):
    deadline=monotonic()+3
    while not predicate():
        if monotonic()>deadline: raise AssertionError('timed out')
        sleep(.005)


def test_interactive_request_precedes_next_background_chunk_and_recursion_is_safe():
    gate=ProviderPriorityLock(); order=[]; release=Event(); held=Event()
    def warmer():
        with background_market_work(lambda: None):
            with gate:
                with gate: held.set(); release.wait(3)
                order.append('chunk1')
            with gate: order.append('chunk2')
    def interactive():
        with gate: order.append('interactive')
    warm=Thread(target=warmer); warm.start(); assert held.wait(3)
    foreground=Thread(target=interactive); foreground.start()
    wait_for(lambda: gate.interactive_waiters==1)
    release.set(); warm.join(3); foreground.join(3)
    assert not warm.is_alive() and not foreground.is_alive()
    assert order==['chunk1','interactive','chunk2']


def test_waiting_background_can_pause_without_acquiring_provider():
    gate=ProviderPriorityLock(); cancelled=Event(); stopped=Event()
    def check():
        if cancelled.is_set(): raise WarmupPaused()
    def warm():
        try:
            with background_market_work(check):
                with gate: pytest.fail('must not acquire interactive lock')
        except WarmupPaused: stopped.set()
    with gate:
        worker=Thread(target=warm); worker.start(); cancelled.set()
        assert stopped.wait(3)
    worker.join(3)


def test_next_chunk_bridges_distant_existing_coverage_in_bounded_steps():
    end=datetime(2026,1,31,tzinfo=timezone.utc); start=end-timedelta(days=30)
    assert next_chunk(start,end,(end+timedelta(days=50),end+timedelta(days=60)))==(end+timedelta(days=43),end+timedelta(days=50))


def test_nq_warm_restart_reuses_dated_contracts_and_provenance(setup, tmp_path):
    from tests.test_continuous_execution import provider, ROLL
    from app.services.market_data import MarketDataService
    from app.storage.market_store import MarketStore
    from app.storage.market_cache_repository import MarketCacheRepository
    manager,_,db=setup
    p=provider(tmp_path)
    market=MarketDataService(p,MarketStore(tmp_path/'market'),MarketCacheRepository(db))
    manager.market_data=market
    job=manager.start(['NQ1!'],lookback_days=3)
    start,end=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime()
    manager.jobs[job['id']]['items'][0].update(requested_start=start.isoformat(),requested_end=end.isoformat(),end_checked=True)
    manager.executor.run()
    assert manager.get(job['id'])['status']=='completed'
    count=len(p.http.calls)
    manager.close()
    restarted=MarketDataService(p,MarketStore(tmp_path/'market'),MarketCacheRepository(db))
    actual=restarted.get_execution_bars('NQ1!','1m',start,end)
    assert actual.source_contract.tolist()==['NQM6','NQU6']
    assert actual.close.tolist()==[104.,115.]
    assert len(p.http.calls)==count


def test_api_lists_and_controls_persisted_jobs_without_starting_downloads(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.data import router
    from app.api.dependencies import get_services
    manager,market,_=setup
    app=FastAPI(); app.include_router(router)
    app.dependency_overrides[get_services]=lambda: SimpleNamespace(market_warmup=manager)
    with TestClient(app) as client:
        assert client.get('/data/cache/warm').json()=={'items':[]}
        response=client.post('/data/cache/warm',json={'symbols':['AAPL']})
        assert response.status_code==200
        job=response.json(); assert job['lookback_days']==30
        assert client.get('/data/cache/warm').json()['items'][0]['id']==job['id']
        assert client.post('/data/cache/warm/'+job['id']+'/pause').json()['status']=='paused'
        manager.executor.run()
        assert not market.calls
        assert client.post('/data/cache/warm/'+job['id']+'/resume').json()['status']=='queued'
        manager.executor.run()
        assert client.get('/data/cache/warm/'+job['id']).json()['status']=='completed'
        assert client.post('/data/cache/warm/'+job['id']+'/unknown').status_code==404


def test_cache_commit_before_job_checkpoint_does_not_download_again(setup):
    manager,market,db=setup
    job=manager.start(['AAPL'],lookback_days=7)
    item=job['items'][0]
    market.covered=(datetime.fromisoformat(item['requested_start']),datetime.fromisoformat(item['requested_end']))
    # Simulates a crash after canonical coverage was committed, before job progress.
    recovered=MarketWarmupManager(market,db)
    try:
        recovered.resume(job['id']); recovered.executor.run()
        assert not market.calls
        assert recovered.get(job['id'])['status']=='completed'
    finally: recovered.close()


def test_adjusted_nq_also_builds_chart_cache_when_execution_is_already_covered(setup, tmp_path):
    from tests.test_continuous_execution import provider, ROLL
    from app.services.market_data import MarketDataService
    from app.storage.market_store import MarketStore
    from app.storage.market_cache_repository import MarketCacheRepository
    manager,_,db=setup
    p=provider(tmp_path,back_adjust=True)
    market=MarketDataService(p,MarketStore(tmp_path/'market'),MarketCacheRepository(db))
    start,end=(ROLL-pd.Timedelta(days=2)).to_pydatetime(),(ROLL+pd.Timedelta(days=1)).to_pydatetime()
    market.get_execution_bars('NQ1!','1m',start,end)
    calls=len(p.http.calls)
    manager.market_data=market
    job=manager.start(['NQ1!'],lookback_days=3)
    manager.jobs[job['id']]['items'][0].update(requested_start=start.isoformat(),requested_end=end.isoformat(),end_checked=True)
    manager.executor.run()
    assert manager.get(job['id'])['status']=='completed'
    assert market.cached_coverage('NQ1!','1m')==(start,end)
    assert len(p.http.calls)==calls
    actual=market.get_bars('NQ1!','1m',start,end)
    assert actual.source_contract.tolist()==['NQM6','NQU6']
