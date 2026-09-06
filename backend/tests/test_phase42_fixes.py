from datetime import datetime, timezone

import pandas as pd
import pytest

from app.services.execution_price import ExecutionPriceService
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


class FakeProvider:
    key = "fake"


class FakeMarketData:
    provider = FakeProvider()

    def __init__(self):
        self.calls = []

    def get_bars(self, ticker, timeframe, start, end, *, force_refresh=False):
        self.calls.append(force_refresh)
        return pd.DataFrame(
            {
                "timestamp": pd.to_datetime([
                    "2026-08-27T14:59:00Z",
                    "2026-08-27T15:00:00Z",
                    "2026-08-27T15:01:00Z",
                ], utc=True),
                "open": [226.0, 227.0, 228.0],
                "high": [227.0, 228.0, 229.0],
                "low": [225.5, 226.5, 227.5],
                "close": [226.5, 227.25, 228.5],
                "volume": [100, 200, 150],
            }
        )


def test_execution_price_uses_timestamp_column_not_dataframe_index():
    market = FakeMarketData()
    service = ExecutionPriceService(market)
    resolved = service.resolve("NVDA", datetime(2026, 8, 27, 15, 0, 20, tzinfo=timezone.utc))
    assert resolved["price"] == pytest.approx(227.25)
    assert resolved["timestamp"].startswith("2026-08-27T15:00:00")
    assert resolved["source"] == "fake_1m_close_estimate"


class EmptyThenData(FakeMarketData):
    def get_bars(self, ticker, timeframe, start, end, *, force_refresh=False):
        self.calls.append(force_refresh)
        if not force_refresh:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        return super().get_bars(ticker, timeframe, start, end, force_refresh=force_refresh)


def test_execution_price_retries_empty_cache_once():
    market = EmptyThenData()
    resolved = ExecutionPriceService(market).resolve(
        "AAPL", datetime(2026, 8, 27, 15, 0, tzinfo=timezone.utc)
    )
    assert resolved["price"] == pytest.approx(227.25)
    assert True in market.calls


def test_journal_amount_derives_quantity_and_metrics(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    service = JournalService(JournalRepository(db))
    trade = service.create_trade(
        {
            "source": "paper_manual",
            "ticker": "AAPL",
            "direction": "long",
            "entry_price": 200,
            "exit_price": 204,
            "position_amount": 1000,
            "position_currency": "USD",
            "stop_loss": 198,
            "fees": 0,
        }
    )
    assert trade["quantity"] == pytest.approx(5)
    assert trade["position_amount"] == pytest.approx(1000)
    assert trade["pnl_amount"] == pytest.approx(20)
    assert trade["pnl_pct"] == pytest.approx(2)
    assert trade["r_multiple"] == pytest.approx(2)
    assert trade["result"] == "win"
