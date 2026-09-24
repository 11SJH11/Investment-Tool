import sqlite3

from app.storage.database import Database


def test_phase4_initialize_preserves_existing_phase3_data(tmp_path):
    path = tmp_path / "ledger.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE securities(ticker TEXT PRIMARY KEY,name TEXT NOT NULL,asset_type TEXT NOT NULL DEFAULT 'equity',security_type TEXT NOT NULL DEFAULT 'common_stock',exchange TEXT,status TEXT,tradable INTEGER,fractionable INTEGER,shortable INTEGER,provider TEXT NOT NULL,provider_id TEXT,cik TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("INSERT INTO securities(ticker,name,provider) VALUES ('AAPL','Apple','alpaca')")
    connection.commit(); connection.close()

    db = Database(path)
    db.initialize()
    with db.connect() as c:
        assert c.execute("SELECT name FROM securities WHERE ticker='AAPL'").fetchone()[0] == "Apple"
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "journal_trades" in tables
    assert "portfolio_transactions" in tables


def test_phase41_adds_columns_to_existing_phase4_tables(tmp_path):
    path = tmp_path / "phase4.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE securities(ticker TEXT PRIMARY KEY,name TEXT NOT NULL,asset_type TEXT NOT NULL DEFAULT 'equity',security_type TEXT NOT NULL DEFAULT 'common_stock',exchange TEXT,status TEXT,tradable INTEGER,fractionable INTEGER,shortable INTEGER,provider TEXT NOT NULL,provider_id TEXT,cik TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("CREATE TABLE portfolio_transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,account TEXT NOT NULL DEFAULT 'Main',ticker TEXT NOT NULL,action TEXT NOT NULL,occurred_at TEXT NOT NULL,quantity REAL NOT NULL,price REAL NOT NULL,fees REAL NOT NULL DEFAULT 0,note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("CREATE TABLE journal_trades(id INTEGER PRIMARY KEY AUTOINCREMENT,source TEXT NOT NULL,name TEXT NOT NULL DEFAULT 'Trade',account TEXT NOT NULL DEFAULT 'Main',ticker TEXT NOT NULL,direction TEXT NOT NULL DEFAULT 'long',status TEXT NOT NULL DEFAULT 'open',opened_at TEXT,closed_at TEXT,entry_price REAL,exit_price REAL,quantity REAL,stop_loss REAL,take_profit REAL,fees REAL NOT NULL DEFAULT 0,result TEXT,result_source TEXT,pnl_amount REAL,pnl_pct REAL,r_multiple REAL,trade_type TEXT NOT NULL DEFAULT '',setup TEXT NOT NULL DEFAULT '',market_condition TEXT NOT NULL DEFAULT '',entry_timeframe TEXT NOT NULL DEFAULT '',timeframe_alignment TEXT NOT NULL DEFAULT '',dxy TEXT NOT NULL DEFAULT '',session_time TEXT NOT NULL DEFAULT '',tf_type TEXT NOT NULL DEFAULT '',wick TEXT NOT NULL DEFAULT '',analysis TEXT NOT NULL DEFAULT '',entry_notes TEXT NOT NULL DEFAULT '',management TEXT NOT NULL DEFAULT '',learning TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',timeframe_notes TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("INSERT INTO securities(ticker,name,provider) VALUES ('NVDA','NVIDIA','alpaca')")
    connection.execute("INSERT INTO portfolio_transactions(account,ticker,action,occurred_at,quantity,price,fees,note) VALUES ('Main','NVDA','BUY','2026-08-27T21:27:00Z',0.5,200,0,'legacy')")
    connection.execute("INSERT INTO journal_trades(source,ticker) VALUES ('paper_manual','NVDA')")
    connection.commit(); connection.close()

    db = Database(path)
    db.initialize()
    with db.connect() as c:
        pcols = {row[1] for row in c.execute("PRAGMA table_info(portfolio_transactions)")}
        jcols = {row[1] for row in c.execute("PRAGMA table_info(journal_trades)")}
        assert {"input_mode","input_amount","base_currency","fx_rate","price_source"} <= pcols
        assert {"pnl_override","override_reason","pnl_source","practised_at"} <= jcols
        assert c.execute("SELECT note FROM portfolio_transactions WHERE ticker='NVDA'").fetchone()[0] == "legacy"
        assert c.execute("SELECT ticker FROM journal_trades").fetchone()[0] == "NVDA"
