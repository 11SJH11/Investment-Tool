"""Durable local queue. Run one application process; threads share data caches."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import RLock
import json
import uuid


class JobCancelled(Exception):
    pass


class BacktestJobs:
    def __init__(self, database, backtest, workers=2):
        self.database, self.backtest = database, backtest
        self.lock = RLock()
        self.closed = False
        saved_mode = database.get_setting('backtest_worker_mode')
        self.worker_mode = saved_mode or ('auto_conservative' if int(workers) == 2 else str(max(1,min(int(workers),8))))
        from app.services.simulation_budget import SimulationBudget
        self.budget = SimulationBudget(lambda: self.workers)
        self.backtest.simulation_budget = self.budget
        from app.storage.research_experiment_repository import ResearchExperimentRepository
        self.research = ResearchExperimentRepository(database)
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='backtest')
        with database.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS backtest_jobs (
                id TEXT PRIMARY KEY, request_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
                batch_id TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
                processed INTEGER, total INTEGER, run_id INTEGER, error TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(request_key, ordinal))''')
            # Recover a successful immutable save even if the process died before
            # recording completion. Otherwise interrupted work requires explicit retry.
            for row in db.execute("SELECT id,payload FROM backtest_jobs WHERE status IN ('running','preparing data','preparing shared data','analysing results','saving')").fetchall():
                payload = json.loads(row['payload'])
                if payload.get('research_children'):
                    document = self.research.get(payload['experiment_group'])
                    complete = document and document.get('status') == 'completed'
                    db.execute('UPDATE backtest_jobs SET status=?,error=? WHERE id=?',
                               ('completed' if complete else 'failed', None if complete else 'Research interrupted. Retry resumes unsaved cells against the same data fingerprint.', row['id']))
                    continue
                saved = db.execute("SELECT id FROM backtest_runs WHERE json_extract(config_json, '$.queue_job_id')=? ORDER BY id DESC LIMIT 1", (row['id'],)).fetchone()
                db.execute("UPDATE backtest_jobs SET status=?,run_id=?,error=? WHERE id=?",
                           ('completed' if saved else 'failed', saved['id'] if saved else None,
                            None if saved else 'Application stopped before completion. Retry explicitly.', row['id']))
            pending = [row['id'] for row in db.execute("SELECT id FROM backtest_jobs WHERE status='queued' ORDER BY created_at, ordinal")]
        for job_id in pending:
            self.executor.submit(self._work, job_id)

    @property
    def workers(self):
        from app.research_runtime import worker_count
        return worker_count(self.worker_mode)

    def compute_settings(self):
        with self.database.connect() as db:
            pending = db.execute("""SELECT coalesce(sum(
                CASE WHEN json_array_length(payload,'$.research_children') > 0
                THEN max(0,json_array_length(payload,'$.research_children')-coalesce(processed,0))
                ELSE 1 END),0) FROM backtest_jobs
                WHERE status IN ('queued','preparing data','preparing shared data','running')
                AND cancel_requested=0""").fetchone()[0]
        snapshot = self.budget.snapshot()
        return {'mode': self.worker_mode, 'resolved_workers': self.workers, **snapshot,
                'queued_simulations': max(0, pending-snapshot['used_workers']),
                'note': 'Used workers are reserved CPU slots shared by ordinary runs and research pools. Lowering the budget lets current work drain before admitting more.'}

    def set_worker_mode(self, mode):
        from app.research_runtime import worker_count
        mode = str(mode or '').strip()
        if mode == 'auto':
            mode = 'auto_conservative'
        if mode not in {'auto_conservative','auto_performance','1','2','3','4','5','6','7','8'}:
            raise ValueError('Compute mode must be Auto conservative, Auto performance or 1–8 workers')
        worker_count(mode)  # validate on this host
        self.worker_mode = mode
        self.database.set_setting('backtest_worker_mode', mode)
        self.budget.notify()
        return self.compute_settings()

    def list(self):
        with self.database.connect() as db:
            rows = db.execute('SELECT * FROM backtest_jobs ORDER BY created_at DESC, rowid DESC LIMIT 500').fetchall()
        return [self._decode(row) for row in rows]

    def compact_list(self):
        with self.database.connect() as db:
            rows=db.execute("""SELECT id,batch_id,status,processed,total,run_id,error,cancel_requested,created_at,updated_at,
                json_object('run_name',json_extract(payload,'$.run_name'),
                            'strategy_key',json_extract(payload,'$.strategy_key'),
                            'symbols',json_extract(payload,'$.symbols'),
                            'experiment_group',json_extract(payload,'$.experiment_group'),
                            'experiment_type',json_extract(payload,'$.experiment_type'),
                            'research_count',coalesce(json_array_length(payload,'$.research_children'),0)) AS payload
                FROM backtest_jobs ORDER BY created_at DESC,rowid DESC LIMIT 500""").fetchall()
        return [self._decode(row) for row in rows]

    @staticmethod
    def _decode(row):
        item = dict(row)
        item['payload'] = json.loads(item['payload'])
        return item

    def get(self, job_id):
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM backtest_jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise ValueError('Job not found')
        return self._decode(row)

    def enqueue(self, payloads, request_key):
        if not request_key or len(request_key) > 100 or not 1 <= len(payloads) <= 100:
            raise ValueError('Provide a request key and between 1 and 100 independent runs')
        canonical = []
        for payload in payloads:
            symbols = payload.get('symbols', [])
            if isinstance(symbols, str):
                symbols = symbols.replace(',', ' ').split()
            if len(symbols) != 1:
                raise ValueError('Each queued run must contain exactly one symbol; batch runs use independent capital')
            canonical.append({**payload, 'symbols': [symbols[0].strip().upper()], 'save_run': True})
        with self.lock:
            if self.closed:
                raise ValueError('Queue is shutting down')
            with self.database.connect() as db:
                existing = db.execute('SELECT * FROM backtest_jobs WHERE request_key=? ORDER BY ordinal', (request_key,)).fetchall()
                if existing:
                    if [json.loads(row['payload']) for row in existing] != canonical:
                        raise ValueError('Request key already belongs to a different submission')
                    return [self._decode(row) for row in existing]
                for payload in canonical:
                    if payload.get('research_children'):
                        active=db.execute("SELECT id FROM backtest_jobs WHERE json_extract(payload,'$.experiment_group')=? AND status IN ('queued','preparing data','preparing shared data','running','analysing results','saving')",(payload['experiment_group'],)).fetchone()
                        if active:
                            raise ValueError('This research experiment is already queued or running')
                ids = [str(uuid.uuid4()) for _ in canonical]
                for index, (job_id, payload) in enumerate(zip(ids, canonical)):
                    db.execute("INSERT INTO backtest_jobs(id,request_key,ordinal,batch_id,payload,status) VALUES(?,?,?,?,?,'queued')",
                               (job_id, request_key, index, request_key, json.dumps(payload)))
            for job_id in ids:
                self.executor.submit(self._work, job_id)
            return [self.get(job_id) for job_id in ids]

    def _update(self, job_id, **values):
        with self.database.connect() as db:
            db.execute(f"UPDATE backtest_jobs SET {','.join(key+'=?' for key in values)},updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (*values.values(), job_id))

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job['status'] == 'queued':
                self._update(job_id, status='cancelled', cancel_requested=1)
            elif job['status'] in ('preparing data', 'running', 'preparing shared data', 'analysing results', 'saving'):
                self._update(job_id, cancel_requested=1)
            return self.get(job_id)


    def delete(self, job_id):
        """Delete one terminal queue record without deleting its saved backtest run."""
        with self.lock:
            job = self.get(job_id)
            if job['status'] not in ('completed', 'failed', 'cancelled'):
                raise ValueError('Only completed, failed or cancelled jobs can be deleted')
            with self.database.connect() as db:
                db.execute('DELETE FROM backtest_jobs WHERE id=?', (job_id,))
        return {'ok': True, 'job_id': job_id, 'run_id': job.get('run_id')}

    def clear_finished(self):
        """Remove terminal queue history only; immutable saved runs remain untouched."""
        with self.lock:
            with self.database.connect() as db:
                row = db.execute("SELECT COUNT(*) AS n FROM backtest_jobs WHERE status IN ('completed','failed','cancelled')").fetchone()
                count = int(row['n'] or 0)
                db.execute("DELETE FROM backtest_jobs WHERE status IN ('completed','failed','cancelled')")
        return {'ok': True, 'deleted': count}
    def retry(self, job_id, request_key):
        job = self.get(job_id)
        if job['status'] != 'failed' and not (job['status']=='cancelled' and job['payload'].get('research_children')):
            raise ValueError('Only failed jobs can be retried')
        return self.enqueue([job['payload']], request_key)

    def _work(self, job_id):
        # Parent coordinators/data preparation do not consume CPU reservations.
        # Legacy service doubles without prepare still use one bounded run slot.
        if hasattr(self.backtest, 'prepare'):
            self._work_inner(job_id)
        else:
            try:
                with self.budget.reserve(1, lambda: self._cancelled(job_id)):
                    self._work_inner(job_id)
            except JobCancelled:
                self._update(job_id, status='cancelled')

    def _cancelled(self, job_id):
        if self.closed or self.get(job_id)['cancel_requested']:
            raise JobCancelled()

    def _work_inner(self, job_id):
        try:
            with self.lock:
                if self.closed or self.get(job_id)['status'] != 'queued':
                    return
                self._update(job_id, status='preparing data')
            def progress(status, done, total):
                with self.lock:
                    if self.closed or self.get(job_id)['cancel_requested']:
                        raise JobCancelled()
                    self._update(job_id, status=status, processed=done, total=total)
            def persist(save):
                # Cancellation and commit are mutually exclusive. Once saved,
                # cancellation cannot retroactively remove a successful result.
                with self.lock:
                    progress('running', None, None)
                    saved = save()
                    self._update(job_id, status='completed', run_id=saved['id'])
                    return saved
            payload = {**self.get(job_id)['payload'], 'queue_job_id': job_id}
            if payload.get('research_children') and payload.get('research_workers') == 'global':
                payload['research_workers'] = self.worker_mode
            if payload.get('research_children'):
                from app.services.research_runner import run_experiment
                def cancelled():
                    if self.closed or self.get(job_id)['cancel_requested']:
                        raise JobCancelled()
                def commit(save):
                    with self.lock:
                        cancelled()
                        return save()
                document = run_experiment(self.backtest,self.research,payload,progress=progress,cancelled=cancelled,commit=commit)
                with self.lock:
                    cancelled()
                    failed = sum(c['status'] != 'completed' for c in document['cells'])
                    self._update(job_id,status='failed' if failed else 'completed',
                                 error=f'{failed} research cells failed. Open the experiment for details; retry resumes incomplete cells.' if failed else None)
                return
            if hasattr(self.backtest, 'prepare'):
                prepared = self.backtest.prepare(payload, progress=progress)
                with self.budget.reserve(1, lambda: self._cancelled(job_id)):
                    self.backtest.run(payload, progress=progress, persist=persist, prepared=prepared)
            else:
                self.backtest.run(payload, progress=progress, persist=persist)
            if self.get(job_id)['status'] != 'completed':
                raise RuntimeError('No immutable result was saved')
        except JobCancelled:
            self._update(job_id, status='cancelled')
        except Exception:
            # Provider exceptions may contain request URLs or credentials.
            # Do not log or persist arbitrary exception text.
            self._update(job_id, status='failed', error='Backtest failed. Check strategy, dates, provider configuration and data availability, then retry.')
            payload = self.get(job_id)['payload']
            if payload.get('research_children'):
                document = self.research.get(payload['experiment_group'])
                if document:
                    document['status']='failed'
                    document['error']='Research interrupted or input snapshot changed. Completed cells remain saved; retry only with identical source data.'
                    self.research.save(document)

    def close(self):
        with self.lock:
            self.closed = True
        self.budget.notify()
        self.executor.shutdown(wait=True, cancel_futures=True)
