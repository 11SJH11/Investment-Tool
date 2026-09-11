import sqlite3

from app.data.providers.base import Symbol
from app.data.security_types import infer_security_type
from app.storage.database import Database
from app.storage.screener_repository import ScreenerFilters, ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


def test_security_type_inference_examples():
    assert infer_security_type("Example Technology Inc.") == "common_stock"
    assert infer_security_type("Example Growth ETF") == "etf"
    assert infer_security_type("Example Acquisition Corp. Class A Ordinary Shares") == "spac"
    assert infer_security_type("Example Acquisition Corp. Warrants") == "warrant"
    assert infer_security_type("Example American Depositary Shares") == "adr"
    assert infer_security_type("Example Real Estate Investment Trust REIT") == "reit"


def test_existing_phase3_database_is_migrated_without_rebuild(tmp_path):
    path = tmp_path / "ledger.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE securities (
            ticker TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            asset_type TEXT NOT NULL DEFAULT 'equity',
            exchange TEXT,
            status TEXT,
            tradable INTEGER,
            fractionable INTEGER,
            shortable INTEGER,
            provider TEXT NOT NULL,
            provider_id TEXT,
            cik TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        "INSERT INTO securities(ticker, name, provider) VALUES ('ETF1', 'Example Growth ETF', 'alpaca')"
    )
    connection.commit()
    connection.close()

    db = Database(path)
    db.initialize()
    row = SymbolRepository(db).get("ETF1")
    assert row["security_type"] == "etf"


def test_screener_defaults_to_operating_stocks_but_can_show_etfs(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    symbols = SymbolRepository(db)
    symbols.upsert_many([
        Symbol("AAA", "Alpha Inc.", security_type="common_stock", tradable=True),
        Symbol("ETF1", "Example Growth ETF", security_type="etf", tradable=True),
    ], "test")
    repo = ScreenerRepository(db)

    total, rows = repo.screen(ScreenerFilters(tradable=True))
    assert total == 1
    assert rows[0]["ticker"] == "AAA"

    total, rows = repo.screen(ScreenerFilters(security_type="etf", tradable=True))
    assert total == 1
    assert rows[0]["ticker"] == "ETF1"

    total, rows = repo.screen(ScreenerFilters(security_type="all", tradable=True))
    assert total == 2
