import pytest

from app.forward.paper_journal import PaperJournal
from app.storage.journal_repository import JournalRepository
from app.services.journal import JournalService
from tests.test_forward_deployments import repository
from tests.test_paper_gateway import setup, enter, NOW


def roundtrip(setup, partial=False):
    gateway, broker, identifier = setup
    entry = enter(gateway, identifier)
    broker.fill(entry['client_order_id'], 1 if partial else 2, 'canceled' if partial else 'filled')
    broker.orders[entry['client_order_id']]['filled_at'] = '2026-01-02T14:59:00Z'
    broker.quantity = '1' if partial else '2'
    gateway.reconcile(identifier)
    exit_order = gateway.submit(identifier, decision_at=NOW, action='exit', direction='long', price=500)
    broker.fill(exit_order['client_order_id'], int(broker.quantity))
    broker.orders[exit_order['client_order_id']].update(filled_at='2026-01-02T15:00:01Z', filled_avg_price='501')
    broker.quantity = '0'
    gateway.reconcile(identifier)
    return gateway, broker, identifier


@pytest.mark.parametrize('partial', [False, True])
def test_paper_journal_preserves_fills_unknown_costs_identity_and_reviews(setup, partial):
    gateway, broker, identifier = roundtrip(setup, partial)
    journal = PaperJournal(gateway)
    assert journal.sync(identifier)['created'] == 1
    repo = JournalRepository(gateway.database)
    trade = repo.list_trades(source='broker_alpaca_paper')[0]
    assert trade['quantity'] == (1 if partial else 2)
    assert trade['entry_price'] == 500 and trade['exit_price'] == 501
    assert trade['pnl_amount'] is None and trade['fees'] is None and trade['r_multiple'] is None
    assert trade['is_automated'] and trade['execution_source'] == 'strategy'
    assert trade['source_metadata']['mode'] == 'ALPACA_PAPER'
    assert 'paper-account' not in str(trade)
    JournalService(repo).update_trade(trade['id'], {'notes':'Keep this review'})
    assert PaperJournal(gateway).sync(identifier) == {'created':0, 'updated':0}
    assert repo.get_trade(trade['id'])['notes'] == 'Keep this review'
    with pytest.raises(ValueError, match='read-only'):
        JournalService(repo).update_trade(trade['id'], {'entry_price':1})


def test_pending_fills_never_become_completed_journal_trade(setup):
    gateway, broker, identifier = setup
    entry = enter(gateway, identifier)
    broker.fill(entry['client_order_id'], 1, 'partially_filled')
    broker.quantity = '1'
    gateway.reconcile(identifier)
    assert PaperJournal(gateway).sync(identifier)['created'] == 0
    assert not JournalRepository(gateway.database).list_trades()


def test_partial_exits_form_one_weighted_closed_position(setup):
    gateway, broker, identifier = setup
    entry = enter(gateway, identifier)
    broker.fill(entry['client_order_id'], 2)
    broker.orders[entry['client_order_id']]['filled_at'] = '2026-01-02T14:59:00Z'
    broker.quantity = '2'; gateway.reconcile(identifier)
    first = gateway.submit(identifier, decision_at=NOW, action='exit', direction='long', price=500)
    broker.fill(first['client_order_id'], 1, 'canceled')
    broker.orders[first['client_order_id']].update(filled_at='2026-01-02T15:00:01Z',filled_avg_price='501')
    broker.quantity = '1'; gateway.reconcile(identifier)
    journal = PaperJournal(gateway)
    assert journal.sync(identifier)['created'] == 0
    from datetime import timedelta
    gateway.clock = lambda: NOW+timedelta(seconds=2)
    second = gateway.submit(identifier, decision_at=gateway.clock(), action='exit', direction='long', price=500)
    broker.fill(second['client_order_id'], 1)
    broker.orders[second['client_order_id']].update(filled_at='2026-01-02T15:00:02Z',filled_avg_price='503')
    broker.quantity = '0'; gateway.reconcile(identifier)
    assert journal.sync(identifier)['created'] == 1
    trade = JournalRepository(gateway.database).list_trades()[0]
    assert trade['quantity'] == 2 and trade['exit_price'] == 502
    assert len(trade['source_metadata']['executions']) == 3


def test_ambiguous_timestamps_fail_without_mutating_journal(setup):
    gateway, broker, identifier = roundtrip(setup)
    journal = PaperJournal(gateway)
    journal.sync(identifier)
    repo = JournalRepository(gateway.database)
    before = repo.list_trades()
    import json
    with gateway.database.connect() as c:
        for row in c.execute('SELECT client_order_id,document FROM forward_paper_intents').fetchall():
            intent = json.loads(row[1]); intent['broker']['filled_at'] = NOW.isoformat()
            c.execute('UPDATE forward_paper_intents SET document=? WHERE client_order_id=?', (json.dumps(intent),row[0]))
    with pytest.raises(ValueError, match='ambiguous'):
        journal.sync(identifier)
    assert repo.list_trades() == before
