import importlib.util

import pandas as pd
import pytest

from app.storage.market_store import MarketStore


pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("duckdb") is None,
    reason="duckdb is not installed in this test environment",
)


def test_market_store_upserts_namespaced_and_filters_bars(tmp_path):
    store = MarketStore(tmp_path / "market")
    first = pd.DataFrame({
        "timestamp": ["2026-01-01T14:30:00Z", "2026-01-01T14:35:00Z"],
        "open": [10, 11], "high": [11, 12], "low": [9, 10],
        "close": [10.5, 11.5], "volume": [100, 150],
    })
    update = pd.DataFrame({
        "timestamp": ["2026-01-01T14:35:00Z", "2026-01-01T14:40:00Z"],
        "open": [11, 12], "high": [12, 13], "low": [10, 11],
        "close": [11.75, 12.5], "volume": [175, 200],
    })

    store.write_bars("alpaca-sip-split", "AAPL", "5m", first)
    store.write_bars("alpaca-sip-split", "AAPL", "5m", update)
    result = store.read_bars("alpaca-sip-split", "AAPL", "5m", start="2026-01-01 14:35:00+00:00")

    assert len(result) == 2
    assert result.iloc[0]["close"] == 11.75
