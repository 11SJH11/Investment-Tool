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
        self.workers = max(1, min(int(workers), 8))
        self.lock = RLock()
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix='backtest')
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
            for row in db.execute("SELECT id FROM backtest_jobs WHERE status IN ('running','preparing data')").fetchall():
                saved = db.execute("SELECT id FROM backtest_runs WHERE json_extract(config_json, '$.queue_job_id')=? ORDER BY id DESC LIMIT 1", (row['id'],)).fetchone()
                db.execute("UPDATE backtest_jobs SET status=?,run_id=?,error=? WHERE id=?",
                           ('completed' if saved else 'failed', saved['id'] if saved else None,
                            None if saved else 'Application stopped before completion. Retry explicitly.', row['id']))
            pending = [row['id'] for row in db.execute("SELECT id FROM backtest_jobs WHERE status='queued' ORDER BY created_at, ordinal")]
        for job_id in pending:
            self.executor.submit(self._work, job_id)

    def list(self):
        with self.database.connect() as db:
            rows = db.execute('SELECT * FROM backtest_jobs ORDER BY created_at DESC, rowid DESC LIMIT 500').fetchall()
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
            elif job['status'] in ('preparing data', 'running'):
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
        if job['status'] != 'failed':
            raise ValueError('Only failed jobs can be retried')
        return self.enqueue([job['payload']], request_key)

    def _work(self, job_id):
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
            self.backtest.run(payload, progress=progress, persist=persist)
            if self.get(job_id)['status'] != 'completed':
                raise RuntimeError('No immutable result was saved')
        except JobCancelled:
            self._update(job_id, status='cancelled')
        except Exception:
            # Provider exceptions may contain request URLs or credentials.
            # Do not log or persist arbitrary exception text.
            self._update(job_id, status='failed', error='Backtest failed. Check strategy, dates, provider configuration and data availability, then retry.')

    def close(self):
        with self.lock:
            self.closed = True
        self.executor.shutdown(wait=True, cancel_futures=True)
