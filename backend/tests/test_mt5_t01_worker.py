from datetime import timedelta
from threading import Event
import time

import pytest

from app.brokers.base import BrokerHistoryError
from app.forward.mt5_t01_worker import T01DiagnosticWorker
from tests.test_mt5_t01_feed import feed, NOW
from tests.test_mt5_t01_runtime import runtime, bars


def wait_for(check):
    deadline = time.monotonic()+8
    while time.monotonic()<deadline:
        if check(): return
        time.sleep(.01)
    assert check(), 'Worker did not reach expected state'


def state(worker, identifier):
    return worker.report(identifier)['items'][0]


def make(runtime, feed, **kwargs):
    return T01DiagnosticWorker(runtime[0].database, feed[8], runtime=runtime[0],
                               **(dict(clock=lambda:NOW) | kwargs))


def test_real_read_only_worker_records_and_stops_without_orders(runtime, feed):
    worker=make(runtime,feed); identifier=runtime[1]
    try:
        assert worker.report()['items']==[] and feed[6]==[]
        worker.start(identifier,'fixture')
        wait_for(lambda:state(worker,identifier)['persisted_state']=='WAITING')
        row=state(worker,identifier)
        assert row['thread_alive'] and row['state']=='WAITING' and row['last_decision_at']
        assert not row['execution_enabled']
        before=list(feed[6]); worker.start(identifier,'fixture')
        assert feed[6]==before
        stopped=worker.stop(identifier)['items'][0]
        assert stopped['state']=='STOPPED' and not stopped['thread_alive']
        with worker.database.connect() as c:
            assert c.execute('SELECT COUNT(*) FROM mt5_t01_decisions').fetchone()[0]==1
            assert c.execute('SELECT COUNT(*) FROM mt5_execution_attempts').fetchone()[0]==0
    finally: worker.close()


def test_restart_never_resumes_or_claims_old_thread_health(runtime,feed):
    entered,release=Event(),Event()
    def blocked(*args,**kwargs):
        entered.set();release.wait(8);return dict(status='cancelled')
    first=make(runtime,feed,poll=blocked);identifier=runtime[1]
    try:
        first.start(identifier,'fixture'); assert entered.wait(3)
        second=make(runtime,feed,poll=blocked)
        assert second.report()['items'][0]['state']=='RECOVERY_REQUIRED'
        assert not second.report()['items'][0]['thread_alive']
        with pytest.raises(ValueError,match='ownership is still active'):second.start(identifier,'fixture')
        assert feed[6]==[]
        second.close()
    finally: release.set();first.close()


def test_stop_fences_late_commit_even_when_native_read_did_not_cancel(runtime,feed):
    entered,release=Event(),Event()
    def late(runner,connections,identifier,profile,**kwargs):
        entered.set();release.wait(8)
        bar=bars()[0]
        # Deliberately ignore the cancellation callback to exercise commit fencing.
        runner.step(identifier,bar,observed_at=bar['available_at'],equity=10000.,commit_guard=kwargs['commit_guard'])
        return dict(status='decision_recorded')
    worker=make(runtime,feed,poll=late);identifier=runtime[1]
    try:
        worker.start(identifier,'fixture');assert entered.wait(3)
        result=worker.stop(identifier,join_timeout=0)['items'][0]
        assert result['state']=='STOPPING' and result['thread_alive']
        release.set()
        wait_for(lambda:not state(worker,identifier)['thread_alive'])
        assert state(worker,identifier)['state']=='STOPPED'
        with worker.database.connect() as c:
            assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0]==0
    finally:release.set();worker.close()


def test_stale_owner_cannot_commit_after_explicit_recovery(runtime,feed):
    entered,release=Event(),Event()
    def late(runner,connections,identifier,profile,**kwargs):
        entered.set();release.wait(8)
        bar=bars()[0]
        runner.step(identifier,bar,observed_at=bar['available_at'],equity=10000.,commit_guard=kwargs['commit_guard'])
        return dict(status='cancelled')
    first=make(runtime,feed,poll=late); identifier=runtime[1]
    second=make(runtime,feed,clock=lambda:NOW+timedelta(seconds=61),
                poll=lambda *a,**k:dict(status='waiting_for_completed_minute'))
    try:
        first.start(identifier,'fixture');assert entered.wait(3)
        second.start(identifier,'fixture')
        # Recovery occurs after the initial session minute: wait for the next
        # session rather than backfilling a decision that was never observed.
        wait_for(lambda:state(second,identifier)['state']=='WAITING_SESSION')
        release.set();wait_for(lambda:not first.tasks[identifier]['thread'].is_alive())
        assert state(second,identifier)['state']=='WAITING_SESSION'
        with first.database.connect() as c:
            assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0]==0
    finally:release.set();first.close();second.close()


@pytest.mark.parametrize('failure',[ValueError('SECRET'),BrokerHistoryError('SECRET',category='history')])
def test_failures_are_persisted_and_sanitized(runtime,feed,failure):
    def fail(*a,**k):raise failure
    worker=make(runtime,feed,poll=fail);identifier=runtime[1]
    try:
        worker.start(identifier,'fixture')
        wait_for(lambda:not state(worker,identifier)['thread_alive'])
        row=state(worker,identifier)
        assert row['state']=='FAILED' and row['error_category']
        assert 'SECRET' not in str(row) and feed[6]==[]
    finally:worker.close()


def test_busy_profile_retries_without_hiding_error_and_stops(runtime,feed):
    def busy(*a,**k):raise BrokerHistoryError('busy',category='busy')
    worker=make(runtime,feed,poll=busy);identifier=runtime[1]
    try:
        worker.start(identifier,'fixture')
        wait_for(lambda:state(worker,identifier)['error_category']=='profile_busy')
        assert state(worker,identifier)['state']=='WAITING'
        worker.stop(identifier)
        assert state(worker,identifier)['state']=='STOPPED'
    finally:worker.close()


def test_live_profile_rejected_without_starting_thread(runtime,feed):
    worker=make(runtime,feed);feed[9].environment='live'
    try:
        with pytest.raises(ValueError,match='demo profile'):worker.start(runtime[1],'fixture')
        assert not worker.tasks and worker.report()['items']==[] and feed[6]==[]
    finally:worker.close()


def test_one_worker_per_account_and_no_restart_after_close(runtime,feed):
    entered,release=Event(),Event()
    def blocked(*a,**k):entered.set();release.wait(8);return dict(status='cancelled')
    worker=make(runtime,feed,poll=blocked);runner,identifier,ledger,p=runtime
    other=runner.prepare(ledger,p['id'],symbol='XAUUSDs',stream_key='other',timestamp_policy='verified_utc')
    try:
        worker.start(identifier,'fixture');assert entered.wait(3)
        with pytest.raises(ValueError,match='holds this account'):worker.start(other['id'],'fixture')
        release.set();worker.close()
        with pytest.raises(ValueError,match='closed'):worker.start(identifier,'fixture')
    finally:release.set();worker.close()


def test_heartbeat_age_does_not_claim_health(runtime,feed):
    entered,release=Event(),Event()
    def blocked(*a,**k):entered.set();release.wait(8);return dict(status='cancelled')
    now=[NOW];worker=make(runtime,feed,clock=lambda:now[0],poll=blocked)
    try:
        worker.start(runtime[1],'fixture');assert entered.wait(3)
        now[0]+=timedelta(seconds=61)
        assert state(worker,runtime[1])['state']=='STALLED'
        now[0]=NOW-timedelta(seconds=1)
        assert state(worker,runtime[1])['state']=='STALLED'
    finally:release.set();worker.close()


def test_first_start_waits_for_session_without_contacting_terminal(runtime,feed):
    now=[NOW-timedelta(minutes=2)]
    worker=make(runtime,feed,clock=lambda:now[0]);worker._interval=.01
    try:
        worker.start(runtime[1],'fixture')
        wait_for(lambda:state(worker,runtime[1])['state']=='WAITING_SESSION')
        assert feed[6]==[]
        now[0]=NOW
        wait_for(lambda:state(worker,runtime[1])['last_decision_at'] is not None)
        assert state(worker,runtime[1])['thread_alive']
    finally:worker.close()


def test_close_is_bounded_while_native_call_is_blocked(runtime,feed):
    entered,release=Event(),Event()
    def blocked(*a,**k):entered.set();release.wait(8);return dict(status='cancelled')
    worker=make(runtime,feed,poll=blocked)
    try:
        worker.start(runtime[1],'fixture');assert entered.wait(3)
        start=time.monotonic();worker.close()
        assert time.monotonic()-start<3
        row=state(worker,runtime[1])
        assert row['state']=='STOPPING' and row['thread_alive']
        release.set();wait_for(lambda:not state(worker,runtime[1])['thread_alive'])
        assert state(worker,runtime[1])['state']=='STOPPED'
    finally:release.set();worker.close()
