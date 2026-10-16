import json
import pytest

from app.forward.journal import ShadowJournal
from app.services.journal import JournalService
from app.storage.journal_repository import JournalRepository
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running, minutes


def test_source_migration_preserves_ids_attachments_custom_objects_and_sequence(tmp_path):
    from app.storage.database import Database, _SCHEMA
    db = Database(tmp_path/'legacy.db')
    with db.connect() as c:
        c.executescript(_SCHEMA)
        c.execute("INSERT INTO journal_trades(id,source,ticker,notes) VALUES (7,'paper_manual','QQQ','Keep')")
        c.execute("INSERT INTO journal_trades(id,source,ticker) VALUES (100,'replay','QQQ')")
        c.execute('DELETE FROM journal_trades WHERE id=100')
        c.execute("INSERT INTO media_attachments(owner_type,owner_id,slot,original_name,stored_name,mime_type) VALUES ('trade',7,'1m','chart.png','fixture.png','image/png')")
        c.execute('CREATE INDEX custom_journal_notes ON journal_trades(notes)')
        c.execute('CREATE TABLE audit_fixture(id INTEGER)')
        c.execute('CREATE TRIGGER custom_journal_trigger AFTER UPDATE ON journal_trades BEGIN INSERT INTO audit_fixture VALUES (new.id); END')
    db.initialize()
    db.initialize()
    with db.connect() as c:
        assert c.execute('SELECT notes FROM journal_trades WHERE id=7').fetchone()[0] == 'Keep'
        assert c.execute('SELECT owner_id,slot FROM media_attachments').fetchone()[:] == (7, '1m')
        assert c.execute("SELECT count(*) FROM sqlite_master WHERE name IN ('custom_journal_notes','custom_journal_trigger')").fetchone()[0] == 2
        c.execute("UPDATE journal_trades SET notes='Reviewed' WHERE id=7")
        assert c.execute('SELECT id FROM audit_fixture ORDER BY rowid DESC LIMIT 1').fetchone()[0] == 7
        cursor = c.execute("INSERT INTO journal_trades(source,ticker) VALUES ('forward_shadow','QQQ')")
        assert cursor.lastrowid > 100


def test_closed_shadow_trades_keep_identity_reviews_and_exact_engine_results(running):
    runtime, experiment, _ = running
    journal = ShadowJournal(runtime.database)
    repo = JournalRepository(runtime.database)
    service = JournalService(repo)
    runtime.ingest(experiment, minutes(2))
    assert journal.sync(experiment) == 0  # Open simulated positions are not closed fills.
    final = runtime.ingest(experiment, minutes(6))
    expected = sum(len(d['state']['trade_history']) for d in final)
    assert expected > 0 and journal.sync(experiment) == expected
    trades = repo.list_trades(source='forward_shadow')
    assert len(trades) == expected
    assert len({t['external_id'] for t in trades}) == expected
    assert len({t['external_account_key'] for t in trades}) == 4
    for trade in trades:
        recorded = trade['source_metadata']['trade']
        assert trade['pnl_amount'] == recorded['net_pnl']
        assert trade['r_multiple'] == recorded['r_multiple']
        assert trade['fees'] == recorded['fees']
        assert trade['is_automated'] and trade['execution_source'] == 'strategy'
        assert trade['source_metadata']['simulated'] is True
        assert trade['source_metadata']['feed']['feed'] == 'raw'
        assert trade['source_metadata']['source_archive']['sha256']
    first = trades[0]
    service.update_trade(first['id'], {'notes': 'Keep my review', 'timeframe_notes': {'1m': 'Entry'}})
    assert ShadowJournal(runtime.database).sync(experiment) == 0
    saved = repo.get_trade(first['id'])
    assert saved['notes'] == 'Keep my review' and saved['timeframe_notes'] == {'1m': 'Entry'}
    assert saved['imported_at'] == first['imported_at']
    for payload in ({'entry_price': 1}, {'source_metadata': {}}, {'source': 'live_manual'}):
        with pytest.raises(ValueError, match='read-only'):
            service.update_trade(first['id'], payload)
    with pytest.raises(ValueError, match='Unknown trade source'):
        service.create_trade({'source': 'forward_shadow', 'ticker': 'QQQ'})


def test_changed_closed_shadow_facts_fail_without_overwriting_journal(running):
    runtime, experiment, _ = running
    rows = runtime.ingest(experiment, minutes(6))
    journal = ShadowJournal(runtime.database)
    journal.sync(experiment)
    repo = JournalRepository(runtime.database)
    before = repo.list_trades(source='forward_shadow')
    row = rows[0]
    row['state']['trade_history'][0]['net_pnl'] += 1
    with runtime.database.connect() as c:
        c.execute('UPDATE forward_deployments SET state_json=? WHERE id=?',
                  (json.dumps(row['state']), row['id']))
    with pytest.raises(ValueError, match='changed'):
        journal.sync(experiment)
    assert repo.list_trades(source='forward_shadow') == before
