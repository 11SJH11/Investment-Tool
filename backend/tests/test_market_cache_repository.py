from datetime import datetime, timezone

from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository


def test_market_coverage_extends_without_shrinking(tmp_path):
    database = Database(tmp_path / "ledger.db")
    database.initialize()
    repo = MarketCacheRepository(database)

    repo.extend("alpaca-sip-split", "AAPL", "5m", datetime(2026, 1, 2, tzinfo=timezone.utc), datetime(2026, 1, 3, tzinfo=timezone.utc))
    repo.extend("alpaca-sip-split", "AAPL", "5m", datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 2, 12, tzinfo=timezone.utc))

    start, end = repo.get("alpaca-sip-split", "AAPL", "5m")
    assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 1, 3, tzinfo=timezone.utc)
