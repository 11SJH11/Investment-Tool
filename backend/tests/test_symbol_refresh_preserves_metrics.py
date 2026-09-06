from pathlib import Path

from app.data.providers.base import Symbol
from app.storage.database import Database
from app.storage.screener_repository import ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


def test_replace_all_keeps_metrics_for_symbols_that_remain(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    symbols = SymbolRepository(db)
    symbols.replace_all([Symbol("AAA", "Alpha", tradable=True), Symbol("OLD", "Old", tradable=True)], "test")
    screener = ScreenerRepository(db)
    screener.upsert_fundamentals([{"ticker":"AAA", "company_name":"Alpha", "source":"sec"}])
    symbols.replace_all([Symbol("AAA", "Alpha renamed", tradable=True), Symbol("NEW", "New", tradable=True)], "test")
    assert screener.get_metrics("AAA")["company_name"] == "Alpha"
    assert symbols.get("OLD") is None
    assert symbols.get("NEW") is not None
