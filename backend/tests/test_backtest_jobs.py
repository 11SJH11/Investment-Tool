from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, Lock
from time import monotonic, sleep

import pytest

from app.services.backtest_jobs import BacktestJobs
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.services.market_data import MarketDataService
from app.storage.market_cache_repository import MarketCacheRepository
from tests.test_market_data_service import FakeProvider, MemoryStore


def wait_for(predicate):
    deadline = monotonic() + 8
    while monotonic() < deadline:
        if predicate():
            return
        sleep(.01)
    assert predicate()


class ControlledBacktest:
    def __init__(self, db):
        self.runs = BacktestRunRepository(db)
        self.release = Event()
        self.active = self.maximum = 0
        self.lock = Lock()

    def run(self, payload, *, progress, persist):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            progress('preparing data', None, None)
            while not self.release.wait(.01):
                progress('running', 1, 10)
            if payload.get('fail'):
                raise RuntimeError('SECRET token in unsafe provider exception')
            progress('running', 10, 10)
            persist(lambda: self.runs.create(config=payload, result={'symbols': payload['symbols'], 'metrics': {'trades': 2}}))
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def queue(tmp_path):
    db = Database(tmp_path / 'jobs.db')
    db.initialize()
    service = ControlledBacktest(db)
    jobs = BacktestJobs(db, service)
    yield jobs, service, db
    service.release.set()
    jobs.close()


def test_bounded_batch_states_cancellation_and_immutable_save(queue):
    jobs, service, db = queue
    batch = jobs.enqueue([{'symbols': [s]} for s in ['AAPL', 'MSFT', 'NVDA', 'AMZN']], 'batch')
    wait_for(lambda: service.active == 2)
    assert service.maximum == 2
    assert jobs.get(batch[2]['id'])['status'] == 'queued'
    assert jobs.get(batch[3]['id'])['status'] == 'queued'
    jobs.cancel(batch[2]['id'])
    jobs.cancel(batch[0]['id'])
    wait_for(lambda: jobs.get(batch[0]['id'])['status'] == 'cancelled')
    service.release.set()
    wait_for(lambda: all(j['status'] in ('completed', 'cancelled') for j in jobs.list()))
    assert [jobs.get(j['id'])['status'] for j in batch] == ['cancelled', 'completed', 'cancelled', 'completed']
    assert len(service.runs.list()) == 2
    completed = jobs.get(batch[1]['id'])
    before = service.runs.get(completed['run_id'])
    jobs.cancel(completed['id'])
    assert service.runs.get(completed['run_id']) == before
    assert service.maximum == 2
    db.initialize()
    assert len(jobs.list()) == 4



def test_terminal_job_cleanup_keeps_saved_runs(queue):
    jobs, service, _ = queue
    service.release.set()
    completed = jobs.enqueue([{'symbols': ['AAPL']}], 'cleanup-completed')[0]
    wait_for(lambda: jobs.get(completed['id'])['status'] == 'completed')
    run_id = jobs.get(completed['id'])['run_id']
    assert service.runs.get(run_id)['id'] == run_id
    jobs.delete(completed['id'])
    with pytest.raises(ValueError, match='Job not found'):
        jobs.get(completed['id'])
    assert service.runs.get(run_id)['id'] == run_id

    failed = jobs.enqueue([{'symbols': ['MSFT'], 'fail': True}], 'cleanup-failed')[0]
    wait_for(lambda: jobs.get(failed['id'])['status'] == 'failed')
    cancelled = jobs.enqueue([{'symbols': ['NVDA']}], 'cleanup-cancelled')[0]
    # The worker may start immediately; cancellation is cooperative in either state.
    jobs.cancel(cancelled['id'])
    wait_for(lambda: jobs.get(cancelled['id'])['status'] in ('cancelled', 'completed'))
    result = jobs.clear_finished()
    assert result['deleted'] >= 2
    assert not jobs.list()

def test_duplicate_submission_and_conflicting_key(queue):
    jobs, _, _ = queue
    payload = [{'symbols': ['AAPL']}]
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda _: jobs.enqueue(payload, 'same'), range(6)))
    assert len({result[0]['id'] for result in results}) == 1
    assert len(jobs.list()) == 1
    with pytest.raises(ValueError, match='different'):
        jobs.enqueue([{'symbols': ['MSFT']}], 'same')
    with pytest.raises(ValueError, match='exactly one'):
        jobs.enqueue([{'symbols': ['AAPL', 'MSFT']}], 'portfolio')


def test_failure_redaction_retry_and_restart(queue):
    jobs, service, db = queue
    service.release.set()
    job = jobs.enqueue([{'symbols': ['AAPL'], 'fail': True}], 'fail')[0]
    wait_for(lambda: jobs.get(job['id'])['status'] == 'failed')
    assert 'SECRET' not in str(jobs.list())
    assert not service.runs.list()
    retry = jobs.retry(job['id'], 'retry')[0]
    assert retry['id'] != job['id']
    wait_for(lambda: jobs.get(retry['id'])['status'] == 'failed')
    jobs.close()
    jobs._update(job['id'], status='running')
    jobs._update(retry['id'], status='queued')
    restarted = BacktestJobs(db, service, 1)
    try:
        assert restarted.get(job['id'])['status'] == 'failed'
        assert 'stopped' in restarted.get(job['id'])['error']
        wait_for(lambda: restarted.get(retry['id'])['status'] == 'failed')
    finally:
        restarted.close()


def test_restart_recovers_saved_commit_without_rerun(queue):
    jobs, service, db = queue
    service.release.set()
    job = jobs.enqueue([{'symbols': ['AAPL']}], 'save')[0]
    wait_for(lambda: jobs.get(job['id'])['status'] == 'completed')
    jobs.close()
    jobs._update(job['id'], status='running', run_id=None)
    restarted = BacktestJobs(db, service)
    try:
        assert restarted.get(job['id'])['status'] == 'completed'
        assert restarted.get(job['id'])['run_id'] is not None
        assert len(service.runs.list()) == 1
    finally:
        restarted.close()


@pytest.mark.parametrize('provider_key', ['alpaca', 'oanda', 'massive'])
def test_concurrent_services_share_provider_cache_single_flight(tmp_path, provider_key):
    db = Database(tmp_path / 'cache.db'); db.initialize()
    provider = FakeProvider(); provider.key = provider_key
    store = MemoryStore()
    services = [MarketDataService(provider, store, MarketCacheRepository(db)) for _ in range(6)]
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 3, tzinfo=timezone.utc)
    with ThreadPoolExecutor(6) as pool:
        frames = list(pool.map(lambda service: service.get_bars('AAPL', '5m', start, end), services))
    assert len(provider.calls) == 1
    assert all(frame.equals(frames[0]) for frame in frames)


def test_real_service_queue_saves_same_engine_result_and_normalised_config(tmp_path):
    from app.services.backtest import BacktestService
    from tests.test_intraday_baselines import vwap_frame
    from app.backtesting.strategies.intraday_baselines import VWAP
    class Market:
        def get_bars(self, *args):
            return vwap_frame().copy()
    db = Database(tmp_path / 'real.db'); db.initialize()
    service = BacktestService(Market(), BacktestRunRepository(db))
    payload = dict(strategy_key=VWAP, symbols=['AAPL'], primary_timeframe='1m',
                   start_date='2026-01-05', end_date='2026-01-05')
    direct = service.run({**payload, 'save_run': False})
    queue = BacktestJobs(db, service)
    try:
        job = queue.enqueue([payload], 'real')[0]
        wait_for(lambda: queue.get(job['id'])['status'] in ('completed', 'failed'))
        assert queue.get(job['id'])['status'] == 'completed'
        saved = service.get_run(queue.get(job['id'])['run_id'])
        assert saved['result']['trades'] == direct['trades']
        assert saved['result']['metrics'] == direct['metrics']
        assert saved['config']['strategy_params'] == direct['strategy']['params']
        assert saved['config']['queue_job_id'] == job['id']
        summary = service.list_runs()[0]
        assert summary['win_rate_pct'] == direct['metrics']['win_rate_pct']
        assert summary['profit_factor_r'] == direct['metrics']['profit_factor_r']
    finally:
        queue.close()


def test_engine_cooperative_cancellation_propagates_without_result():
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    from app.backtesting.strategies.intraday_baselines import VwapMeanReversion
    from app.services.backtest_jobs import JobCancelled
    from tests.test_intraday_baselines import vwap_frame
    seen = []
    def cancel(done, total):
        seen.append((done, total))
        raise JobCancelled()
    with pytest.raises(JobCancelled):
        BacktestEngine(BacktestConfig()).run(symbol_frames={'AAPL': {'1m': vwap_frame()}},
            strategies={'AAPL': VwapMeanReversion()}, primary_timeframe='1m', progress=cancel)
    assert seen == [(0, 24)]


def test_queue_api_validates_independent_jobs_and_deduplicates(queue):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.strategy_lab import router
    from app.api.dependencies import get_services
    jobs, _, _ = queue
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_services] = lambda: SimpleNamespace(backtest_jobs=jobs)
    payload = dict(strategy_key='test', symbols=['AAPL'], start_date='2026-01-05', end_date='2026-01-05')
    with TestClient(app) as client:
        request = dict(request_key='api', runs=[payload])
        first = client.post('/strategy-lab/jobs', json=request)
        second = client.post('/strategy-lab/jobs', json=request)
        assert first.status_code == second.status_code == 200
        job_id = first.json()['jobs'][0]['id']
        assert second.json()['jobs'][0]['id'] == job_id
        assert client.get('/strategy-lab/jobs').json()['max_workers'] == 2
        assert client.post(f'/strategy-lab/jobs/{job_id}/cancel').status_code == 200
        assert client.post('/strategy-lab/jobs/missing/cancel').status_code == 404
        # Active jobs cannot be deleted; terminal queue history can be cleared without touching saved runs.
        active_delete = client.delete(f'/strategy-lab/jobs/{job_id}')
        assert active_delete.status_code in (200, 409)
        invalid = {**payload, 'symbols': ['AAPL', 'MSFT']}
        assert client.post('/strategy-lab/jobs', json=dict(request_key='bad', runs=[invalid])).status_code == 400


def test_worker_configuration_is_bounded_and_preserves_default():
    from app.core.config import Settings
    from pydantic import ValidationError
    assert Settings(_env_file=None).max_concurrent_backtests == 2
    assert Settings(_env_file=None, MAX_CONCURRENT_BACKTESTS=3).max_concurrent_backtests == 3
    for value in [0, 9]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, MAX_CONCURRENT_BACKTESTS=value)
