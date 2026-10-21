"""Progress reporting must not turn SQLite writer contention into a lost run."""
from threading import Event
import sqlite3
import pytest

from app.services.backtest_jobs import BacktestJobs
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from tests.test_backtest_jobs import wait_for


def test_real_sqlite_writer_lock_does_not_abort_simulation(tmp_path,monkeypatch):
    import app.services.backtest_jobs as module
    errors=[];original=module.safe_failure
    def record(exc,**kwargs):
        errors.append((type(exc).__name__,getattr(exc,'sqlite_errorname',None)))
        return original(exc,**kwargs)
    monkeypatch.setattr(module,'safe_failure',record)
    db=Database(tmp_path/'jobs.db');db.initialize()
    class Service:
        def __init__(self):
            self.ready=Event();self.proceed=Event();self.progressed=Event();self.finish=Event()
            self.runs=BacktestRunRepository(db)
        def run(self,payload,*,progress,persist):
            self.ready.set()
            assert self.proceed.wait(5)
            progress('running',64,128)
            self.progressed.set()
            assert self.finish.wait(5)
            progress('running',128,128)
            persist(lambda:self.runs.create(config=payload,result={'symbols':['XAUUSD'],'metrics':{'trades':2}}))
    service=Service();jobs=BacktestJobs(db,service,1)
    writer=db.connect()
    try:
        job=jobs.enqueue([{'symbols':['XAUUSD']}],'contention')[0]
        assert service.ready.wait(5)
        writer.execute('BEGIN IMMEDIATE')
        writer.execute('UPDATE backtest_jobs SET total=total WHERE id=?',(job['id'],))
        service.proceed.set()
        # A progress-only write must not wait the default 5 seconds or fail the
        # simulation. The authoritative result is still committed after release.
        assert service.progressed.wait(6),errors
        writer.rollback()
        service.finish.set()
        wait_for(lambda:jobs.get(job['id'])['status']=='completed')
        assert len(service.runs.list())==1
        assert jobs.get(job['id'])['error'] is None
        assert not errors
    finally:
        writer.rollback();writer.close()
        service.proceed.set();service.finish.set();jobs.close()


@pytest.mark.parametrize('code,category',[(sqlite3.SQLITE_BUSY,'database_busy'),
    (sqlite3.SQLITE_LOCKED,'database_busy'),(sqlite3.SQLITE_BUSY | (2<<8),'database_busy'),
    (sqlite3.SQLITE_FULL,'storage'),(sqlite3.SQLITE_IOERR,'storage')])
def test_contention_classification_and_critical_writes_are_not_suppressed(code,category):
    from app.core.safe_errors import safe_failure
    from types import SimpleNamespace
    error=sqlite3.OperationalError('sensitive diagnostic must not be displayed')
    error.sqlite_errorcode=code
    def fail(**kwargs):raise error
    jobs=BacktestJobs.__new__(BacktestJobs)
    jobs.database=SimpleNamespace(connect=fail)
    assert safe_failure(error)[0]==category
    assert 'sensitive' not in safe_failure(error)[1]
    if category=='database_busy':
        assert jobs._update('job',_progress=True,status='running') is False
    else:
        with pytest.raises(sqlite3.OperationalError):
            jobs._update('job',_progress=True,status='running')
    with pytest.raises(sqlite3.OperationalError):
        jobs._update('job',status='completed',run_id=1)


def test_progress_is_throttled_but_cancellation_is_checked_every_time(tmp_path,monkeypatch):
    db=Database(tmp_path/'throttle.db');db.initialize()
    class Service:
        runs=BacktestRunRepository(db)
        def run(self,payload,*,progress,persist):
            for i in range(100):progress('running',i,100)
            progress('running',100,100)
            persist(lambda:self.runs.create(config=payload,result={'symbols':['XAUUSD'],'metrics':{}}))
    jobs=BacktestJobs(db,Service(),1)
    original=jobs._update;writes=[];checks=[];cancel=jobs._cancelled
    def update(identifier,**kwargs):
        if kwargs.get('_progress'):writes.append(kwargs)
        return original(identifier,**kwargs)
    def checked(identifier):checks.append(identifier);return cancel(identifier)
    monkeypatch.setattr(jobs,'_update',update)
    monkeypatch.setattr(jobs,'_cancelled',checked)
    monkeypatch.setattr('app.services.backtest_jobs.monotonic',lambda:10.)
    try:
        job=jobs.enqueue([{'symbols':['XAUUSD']}],'throttle')[0]
        wait_for(lambda:jobs.get(job['id'])['status']=='completed')
        assert [w['processed'] for w in writes]==[0,100]
        assert len(checks)>=102
    finally:jobs.close()
