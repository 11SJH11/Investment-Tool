from app.storage.database import Database


def test_phase4_schema_tables_exist(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    with db.connect() as c:
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"portfolio_transactions","journal_trades","daily_reviews","playbook_entries","media_attachments"} <= tables
