from datetime import timedelta
import pytest

from app.brokers.base import BrokerHistoryError
from app.forward.mt5_t01_poll import poll_once
from app.forward.mt5_t01_runtime import T01DecisionRuntime
from tests.test_mt5_t01_feed import feed, NOW
from tests.test_mt5_t01_runtime import runtime


def poll(runtime, feed, **changes):
    runner, identifier = runtime[:2]
    return poll_once(runner, feed[8], identifier, 'fixture', **(dict(clock=lambda:NOW) | changes))


def revision(runtime):
    with runtime[0].database.connect() as c:
        return c.execute('SELECT revision FROM mt5_t01_diagnostics WHERE id=?', (runtime[1],)).fetchone()[0]


def test_real_collector_to_runtime_is_idempotent_and_preserves_provenance(runtime, feed):
    first = poll(runtime, feed)
    assert first['status'] == 'decision_recorded' and revision(runtime) == 1
    assert first['decision']['observation']['feed_evidence'] == dict(provider='mt5',profile_id='fixture',
        volume_basis='mt5_tick_volume',timestamp_policy='verified_utc',observation_basis='flat_account_before_and_after')
    before = list(feed[6])
    assert poll(runtime, feed)['status'] == 'waiting_for_completed_minute'
    assert feed[6] == before and revision(runtime) == 1
    assert not first['execution_enabled']


def test_restart_advances_exact_next_minute_after_overlap_verification(runtime, feed):
    poll(runtime, feed)
    runner, identifier, ledger, p = runtime
    restarted = (T01DecisionRuntime(runner.database), identifier, ledger, p)
    now = NOW+timedelta(minutes=1)
    feed[0]._clock = lambda:now.timestamp()
    feed[4].time_msc = int(now.timestamp()*1000)
    feed[5].append(dict(feed[5][0],time=feed[5][0]['time']+60))
    result = poll(restarted, feed, clock=lambda:now)
    assert result['status'] == 'decision_recorded' and revision(runtime) == 2
    assert result['decision']['decision_at'] == now.replace(second=0).isoformat()


@pytest.mark.parametrize('delta', [-60,120,86400])
def test_missed_minute_and_clock_rollback_do_not_fetch_or_advance(runtime, feed, delta):
    poll(runtime, feed); before = list(feed[6])
    with pytest.raises(ValueError, match='recovery required'):
        poll(runtime, feed, clock=lambda:NOW+timedelta(seconds=delta))
    assert revision(runtime) == 1 and feed[6] == before


@pytest.mark.parametrize('after_read', [False,True])
def test_cancellation_does_not_commit_and_cleans_connection(runtime, feed, after_read):
    values = iter([False, True] if after_read else [True])
    assert poll(runtime, feed, cancelled=lambda:next(values))['status'] == 'cancelled'
    assert revision(runtime) == 0
    if after_read:
        assert feed[6][-1] == ('close',) and not feed[8]._profile_locks['fixture'].locked()
    else:
        assert feed[6] == []


def test_provider_failure_retains_frontier_and_can_retry(runtime, feed):
    original = feed[1].copy_rates_range
    feed[1].copy_rates_range = lambda *args:None
    with pytest.raises(BrokerHistoryError): poll(runtime, feed)
    assert revision(runtime) == 0
    feed[1].copy_rates_range = original
    assert poll(runtime, feed)['status'] == 'decision_recorded'


def test_no_historical_backfill_on_first_start(runtime, feed):
    with pytest.raises(ValueError, match='first observation'):
        poll(runtime, feed, clock=lambda:NOW+timedelta(minutes=1))
    assert revision(runtime) == 0 and feed[6] == []


def test_tampered_frontier_fails_before_native_call(runtime, feed):
    poll(runtime, feed); before = list(feed[6])
    with runtime[0].database.connect() as c:
        c.execute("UPDATE mt5_t01_decisions SET document='{}'")
    with pytest.raises(ValueError, match='integrity'):
        poll(runtime, feed)
    assert revision(runtime) == 1 and feed[6] == before


def test_profile_change_during_read_is_rejected_without_commit(runtime, feed):
    original = feed[1].copy_rates_range
    def change(*args):
        result = original(*args)
        feed[8]._setting = lambda key:'b'*64
        return result
    feed[1].copy_rates_range = change
    with pytest.raises(BrokerHistoryError, match='profile changed'):
        poll(runtime, feed)
    assert revision(runtime) == 0
    assert feed[6][-1] == ('close',) and not feed[8]._profile_locks['fixture'].locked()
