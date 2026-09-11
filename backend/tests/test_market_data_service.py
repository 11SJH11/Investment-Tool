from datetime import datetime, timezone

import pandas as pd

from app.services.market_data import MarketDataService
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository


class FakeProvider:
    key = "fake"
    cache_namespace = "fake-feed-split"

    def __init__(self):
        self.calls = []

    def get_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe, start, end))
        return pd.DataFrame({
            "timestamp": [start],
            "open": [10], "high": [11], "low": [9], "close": [10.5], "volume": [100],
        })


class MemoryStore:
    def __init__(self):
        self.frames = []

    def write_bars(self, namespace, ticker, timeframe, bars):
        self.frames.append(bars.copy())

    def read_bars(self, namespace, ticker, timeframe, start=None, end=None):
        if not self.frames:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        return pd.concat(self.frames, ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")


def test_market_data_service_fetches_only_missing_coverage(tmp_path):
    database = Database(tmp_path / "ledger.db")
    database.initialize()
    coverage = MarketCacheRepository(database)
    provider = FakeProvider()
    store = MemoryStore()
    service = MarketDataService(provider, store, coverage)

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    middle = datetime(2026, 1, 2, tzinfo=timezone.utc)
    end = datetime(2026, 1, 3, tzinfo=timezone.utc)

    service.get_bars("AAPL", "5m", start, middle)
    service.get_bars("AAPL", "5m", start, middle)
    service.get_bars("AAPL", "5m", start, end)

    assert len(provider.calls) == 2
    assert provider.calls[0][2:] == (start, middle)
    assert provider.calls[1][2:] == (middle, end)
