"""Explicit, durable cache warming; bounded requests yield to interactive work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
import uuid

from app.data.instruments import instrument_spec, normalize_symbol
from app.core.safe_errors import safe_failure
from app.services.market_coordination import background_market_work, WarmupPaused
from app.storage.market_warmup_repository import MarketWarmupRepository

CHUNK_DAYS = 7
ACTIVE = {'queued', 'running', 'pausing'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def interval(value):
    return tuple(datetime.fromisoformat(x) for x in value) if value else None


def next_chunk(start, end, covered, days=CHUNK_DAYS):
    """Extend adjacent coverage so the store never bridges a huge uncached gap."""
    step = timedelta(days=days)
    if covered is None:
        return max(start, end-step), end
    if start < covered[0]:
        return max(start, covered[0]-step), covered[0]
    if end > covered[1]:
        return covered[1], min(end, covered[1]+step)
    return None


def union(a, b):
    if a is None: return b
    if b is None: return a
    return min(a[0], b[0]), max(a[1], b[1])




class MarketWarmupManager:
    def __init__(self, market_data, database):
        self.market_data = market_data
        self.repository = MarketWarmupRepository(database)
        self.lock = RLock()
        self.jobs = {job['id']: job for job in self.repository.list()}
        self.active = set()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='market-warm')
        self.closed = False
        # No surprise startup downloads: interrupted jobs retain their checkpoints
        # and are explicitly resumable from Settings.
        for job in self.jobs.values():
            if job['status'] in ACTIVE:
                job.update(status='paused', provider_state='paused_after_restart', current_chunk=None)
                self.repository.save(job)

    def _save(self, job, **values):
        job.update(values, updated_at=stamp())
        self.repository.save(job)

    def start(self, symbols, *, timeframe='1m', lookback_days=30, refresh=False):
        if self.market_data is None: raise RuntimeError('No market data provider is configured')
        days = max(1, min(int(lookback_days), 3650))
        cleaned = list(dict.fromkeys(normalize_symbol(value) for value in symbols or [] if value.strip()))
        if not cleaned or len(cleaned) > 50: raise ValueError('Choose 1 to 50 favourite symbols')
        with self.lock:
            if self.closed: raise RuntimeError('Cache warmer is stopping')
            for job in self.jobs.values():
                if job['status'] in ACTIVE and (job['symbols'], job['timeframe'], job['lookback_days'], job['refresh']) == (cleaned, timeframe, days, bool(refresh)):
                    return deepcopy(job)
            end = datetime.now(timezone.utc)
            start = end-timedelta(days=days)
            job = dict(id=str(uuid.uuid4()), symbols=cleaned, timeframe=timeframe, lookback_days=days,
                       refresh=bool(refresh), status='queued', completed=0, total=len(cleaned),
                       chunks_completed=0, chunk_days=CHUNK_DAYS, current_chunk=None, provider_state='queued',
                       created_at=stamp(), items=[dict(symbol=s, status='queued', requested_start=start.isoformat(),
                           requested_end=end.isoformat(), downloaded_coverage=None, bars=0) for s in cleaned])
            self.repository.save(job)
            self.jobs[job['id']] = job
            self._submit(job)
            return deepcopy(job)

    def _submit(self, job):
        self.active.add(job['id'])
        self.executor.submit(self._run, job['id'])

    def get(self, job_id):
        with self.lock:
            if job_id not in self.jobs: raise ValueError('Cache warm job not found')
            return deepcopy(self.jobs[job_id])

    def list(self):
        with self.lock:
            return deepcopy(sorted(self.jobs.values(), key=lambda j: j['created_at'], reverse=True)[:100])

    def pause(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None: raise ValueError('Cache warm job not found')
            if job['status'] in ACTIVE:
                self._save(job, status='pausing' if job['status']=='running' else 'paused', provider_state='pause_requested')
            return deepcopy(job)

    def resume(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None: raise ValueError('Cache warm job not found')
            if job_id in self.active or job['status']=='completed': return deepcopy(job)
            retry = job.get('retry_at')
            if retry and datetime.fromisoformat(retry)>datetime.now(timezone.utc):
                raise ValueError('Provider cooldown is still active; resume after the displayed retry time')
            if self.closed: raise RuntimeError('Cache warmer is stopping')
            self._save(job, status='queued', error=None, error_category=None, retry_at=None, provider_state='queued')
            self._submit(job)
            return deepcopy(job)

    def _check(self, job_id):
        with self.lock:
            if self.closed or self.jobs[job_id]['status'] in {'paused', 'pausing'}:
                raise WarmupPaused()

    def _run(self, job_id):
        try:
            with background_market_work(lambda: self._check(job_id)):
                self._check(job_id)
                with self.lock: self._save(self.jobs[job_id], status='running', provider_state='preparing')
                for index in range(len(self.jobs[job_id]['items'])):
                    self._run_symbol(job_id, index)
                with self.lock:
                    self._save(self.jobs[job_id], status='completed', provider_state='idle', current_chunk=None, finished_at=stamp())
        except WarmupPaused:
            with self.lock: self._save(self.jobs[job_id], status='paused', provider_state='paused', current_chunk=None)
        except Exception as exc:
            category, message, retry_at = safe_failure(exc)
            with self.lock:
                self._save(self.jobs[job_id], status='failed', provider_state=category, error_category=category,
                           error=message, retry_at=retry_at)
        finally:
            with self.lock: self.active.discard(job_id)

    def _run_symbol(self, job_id, index):
        self._check(job_id)
        with self.lock:
            job = self.jobs[job_id]
            item = job['items'][index]
            if item['status']=='completed': return
            symbol, tf = item['symbol'], job['timeframe']
            self._save(job, provider_state='checking_available_history')
        if not item.get('end_checked'):
            end = self.market_data.latest_available_end(symbol, tf, datetime.fromisoformat(item['requested_end']))
            with self.lock:
                item.update(requested_end=end.isoformat(), end_checked=True)
                self._save(job)
        start, end = datetime.fromisoformat(item['requested_start']), datetime.fromisoformat(item['requested_end'])
        if end <= start: raise ValueError('No available range')
        future = instrument_spec(symbol).security_type=='continuous_future'
        chart_adjusted = future and getattr(self.market_data.provider_for(symbol), 'back_adjust', False)
        while True:
            self._check(job_id)
            covered = interval(item.get('downloaded_coverage'))
            if not job['refresh']:
                persisted = self.market_data.cached_coverage(symbol, tf, execution=future)
                if chart_adjusted:
                    chart = self.market_data.cached_coverage(symbol, tf)
                    persisted = (max(persisted[0], chart[0]), min(persisted[1], chart[1])) if persisted and chart else None
                    if persisted and persisted[0] >= persisted[1]: persisted = None
                covered = union(covered, persisted)
            chunk = next_chunk(start, end, covered)
            if chunk is None:
                with self.lock:
                    item.update(status='completed', downloaded_coverage=[v.isoformat() for v in covered])
                    self._save(job, completed=sum(i['status']=='completed' for i in job['items']), current_chunk=None)
                return
            a, b = chunk
            with self.lock:
                item['status']='running'
                self._save(job, current_chunk=dict(symbol=symbol, start=a.isoformat(), end=b.isoformat()),
                           provider_state='waiting_or_fetching')
            if future:
                frame = self.market_data.get_execution_bars(symbol, tf, a, b, force_refresh=job['refresh'])
                if chart_adjusted:
                    self._check(job_id)
                    self.market_data.get_bars(symbol, tf, a, b, force_refresh=job['refresh'])
            else:
                frame = self.market_data.get_bars(symbol, tf, a, b, force_refresh=job['refresh'])
            covered = union(covered, chunk)
            with self.lock:
                item.update(downloaded_coverage=[v.isoformat() for v in covered], bars=item['bars']+len(frame))
                self._save(job, chunks_completed=job['chunks_completed']+1, provider_state='chunk_persisted')
            # Next service call reacquires provider coordination at background priority.

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values():
                if job['status'] in ACTIVE:
                    self._save(job, status='pausing' if job['status']=='running' else 'paused', provider_state='stopping')
        self.executor.shutdown(wait=False, cancel_futures=True)
