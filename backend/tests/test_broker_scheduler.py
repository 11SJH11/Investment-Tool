from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import pytest
from app.brokers.base import BrokerHistoryError
from app.services.broker_scheduler import BrokerScheduler
from app.storage.database import Database

class Connections:
    def __init__(self):
        self.profiles={key:SimpleNamespace(provider=key,configured=True) for key in ('oanda','trading212')}
        self.calls=[];self.failure=None
    def _profile(self,key):return self.profiles[key]
    def sync(self,key):
        self.calls.append(key)
        if self.failure:raise self.failure
        return {'status':'success'}

@pytest.fixture
def scheduler(tmp_path):
    db=Database(tmp_path/'db');db.initialize();now=[1000.];connections=Connections()
    scheduler=BrokerScheduler(connections,db,clock=lambda:now[0])
    yield scheduler,connections,now
    scheduler.close()

def test_defaults_persist_disable_and_safe_bounds(scheduler):
    s,c,now=scheduler
    assert s.status('oanda')['interval_seconds']==60
    assert s.status('trading212')['interval_seconds']==300
    with pytest.raises(BrokerHistoryError):s.configure('trading212',True,60)
    s.configure('oanda',False,120);s.tick();now[0]+=500;s.tick()
    assert 'oanda' not in c.calls
    assert s.status('oanda')['enabled'] is False
    other=BrokerScheduler(c,s.database,clock=lambda:now[0])
    assert other.status('oanda')['interval_seconds']==120
    other.close()

def test_schedule_dispatches_without_browser_and_incomplete_credentials_skip(scheduler):
    s,c,now=scheduler;c.profiles['trading212'].configured=False
    done=Event();original=c.sync
    def sync(key):result=original(key);done.set();return result
    c.sync=sync;s.tick();assert not c.calls
    now[0]+=61;s.tick();assert done.wait(5)
    assert c.calls==['oanda']

def test_retry_after_survives_restart_and_last_success_retained(scheduler):
    s,c,now=scheduler;s.sync_now('oanda');last=s.status('oanda')['last_sync_at']
    c.failure=BrokerHistoryError('HTTP 429',status_code=429,retry_after=900)
    with pytest.raises(BrokerHistoryError):s.sync_now('oanda')
    assert s.status('oanda')['retry_until']==now[0]+900
    assert s.status('oanda')['last_sync_at']==last
    with pytest.raises(BrokerHistoryError,match='cooldown'):s.sync_now('oanda')
    assert len(c.calls)==2
    now[0]+=901;c.failure=None;s.sync_now('oanda')
    assert s.status('oanda')['failures']==0

def test_sync_never_overlaps_and_errors_are_sanitized(scheduler):
    s,c,now=scheduler;started,release=Event(),Event()
    def sync(key):started.set();assert release.wait(5);raise RuntimeError('private-token')
    c.sync=sync
    with ThreadPoolExecutor() as pool:
        task=pool.submit(s.sync_now,'oanda');assert started.wait(5)
        with pytest.raises(BrokerHistoryError,match='already running'):s.sync_now('oanda')
        release.set()
        with pytest.raises(BrokerHistoryError,match='last good') as error:task.result()
        assert 'private-token' not in str(error.value)
    assert not s.active
