from app.data.providers.base import Symbol
from app.storage.database import Database
from app.storage.symbol_repository import SymbolRepository


def test_symbol_repository_replaces_searches_and_enriches(tmp_path):
    database = Database(tmp_path / "ledger.db")
    database.initialize()
    repo = SymbolRepository(database)
    repo.replace_all([
        Symbol("AAPL", "Apple Inc.", exchange="NASDAQ", tradable=True),
        Symbol("MSFT", "Microsoft Corporation", exchange="NASDAQ", tradable=True),
        Symbol("BRK.B", "Berkshire Hathaway Inc.", exchange="NYSE", tradable=True),
    ], provider="alpaca")

    changed = repo.apply_cik_map({"AAPL": "320193", "MSFT": "789019"})
    results = repo.search("apple")

    assert repo.count() == 3
    assert changed == 2
    assert results[0]["ticker"] == "AAPL"
    assert repo.get("AAPL")["cik"] == "0000320193"
    assert repo.get("AAPL")["tradable"] is True
