import pytest

from app.brokers.base import BrokerHistoryError
from app.storage.journal_repository import JournalRepository
from tests.test_mt5_import import setup, deal


def test_future_broker_epochs_import_without_future_cursor_or_lost_notes(setup):
    db, t, s = setup
    s.sync('mt5-default')
    journal = JournalRepository(db)
    old = journal.list_trades()[0]
    journal.update_trade(old['id'], {'notes': 'preserve my review'})
    before = journal.list_trades()[0]
    t.deals += [deal(10800, 0, 0, 1, 100, position=20),
                deal(10801, 1, 1, 1, 110, 10, position=20)]
    result = s.sync('mt5-default')
    assert result['created'] == 1 and result['cursor'] == '10000'
    assert result['history_diagnostics']['deals_ahead_of_host'] == 2
    assert result['history_diagnostics']['positions_processed'] == 2
    assert next(r for r in journal.list_trades() if r['id'] == old['id']) == before
    assert s.sync('mt5-default')['created'] == 0
    assert len(journal.list_trades()) == 2


def test_new_partial_and_close_during_read_retry_full_position(setup):
    db, t, s = setup
    t.deals = [deal(1, 0, 0, 2, 100)]
    original = t.history_deals_get
    calls = 0
    def changing(*args, **kwargs):
        nonlocal calls
        if kwargs:
            calls += 1
            if calls == 2:
                t.deals += [deal(11, 1, 1, 1, 110, 10), deal(12, 1, 1, 1, 120, 20)]
        return original(*args, **kwargs)
    t.history_deals_get = changing
    result = s.sync('mt5-default')
    assert result['created'] == 1
    assert result['history_diagnostics']['history_attempts'] == 2
    row = JournalRepository(db).list_trades()[0]
    assert row['exit_price'] == 115 and row['quantity'] == 2
    assert s.sync('mt5-default')['created'] == 0


@pytest.mark.parametrize('failure', ['changing', 'far_future', 'milliseconds', 'missing_detail'])
def test_failed_read_preserves_cursor_and_records_then_successful_retry(setup, failure):
    db, t, s = setup
    s.sync('mt5-default')
    before = JournalRepository(db).list_trades()
    key = before[0]['external_account_key']
    cursor = s.state.state('mt5', key)['cursor']
    original = t.history_deals_get
    def bad(*args, **kwargs):
        rows = original(*args, **kwargs)
        if kwargs:
            if failure == 'changing':
                t.deals[0].price += 1
            elif failure == 'far_future':
                rows = rows + [deal(100000, 1, 1, 1, 110)]
            elif failure == 'milliseconds':
                t.deals[0].time_msc = 2000000
            else:
                rows = []
        return rows
    # Return copies so a later native mutation cannot mutate an earlier read.
    from copy import deepcopy
    t.history_deals_get = lambda *a, **kw: deepcopy(bad(*a, **kw))
    with pytest.raises(BrokerHistoryError):
        s.sync('mt5-default')
    assert JournalRepository(db).list_trades() == before
    assert s.state.state('mt5', key)['cursor'] == cursor
    t.history_deals_get = original
    t.deals[0].price = 100
    t.deals[0].time_msc = 1000
    t.deals += [deal(11, 0, 0, 1, 100, position=20), deal(12, 1, 1, 1, 110, 10, position=20)]
    assert s.sync('mt5-default')['created'] == 1
