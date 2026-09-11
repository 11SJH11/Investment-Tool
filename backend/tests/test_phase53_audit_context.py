from datetime import datetime, timedelta, timezone

import pandas as pd

from app.services.backtest import BacktestService


class FakeProvider:
    historical_delay_minutes = 15
    historical_feed = "sip"
    adjustment = "split"


class FakeMarketData:
    def __init__(self, frame):
        self.frame = frame
        self.provider = FakeProvider()
        self.calls = []

    def get_bars(self, symbol, timeframe, start, end):
        self.calls.append((symbol, timeframe, start, end))
        ts = pd.to_datetime(self.frame["timestamp"], utc=True)
        return self.frame[(ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))].copy()


def regular_session(day: str):
    start = pd.Timestamp(f"{day}T14:30:00Z")  # 09:30 ET in January
    rows = []
    for i in range(78):
        ts = start + pd.Timedelta(minutes=5 * i)
        price = 100 + i / 100
        rows.append([ts, price, price + 0.1, price - 0.1, price + 0.02, 1000])
    return rows


def test_audit_context_counts_filtered_bars_across_previous_trading_day():
    # Friday + Monday. A Monday 09:35 ET entry only has one same-day bar before it,
    # so a correct "50 bars before" request must reach into Friday rather than
    # subtracting only 250 wall-clock minutes and then filtering the premarket away.
    rows = regular_session("2026-01-02") + regular_session("2026-01-05")
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    market = FakeMarketData(frame)
    service = BacktestService(market)

    result = service.audit_bars(
        symbol="AAPL",
        timeframe="5m",
        session="regular",
        entry=datetime(2026, 1, 5, 14, 35, tzinfo=timezone.utc),
        exit=datetime(2026, 1, 5, 14, 50, tzinfo=timezone.utc),
        before_bars=50,
        after_bars=20,
    )

    assert result["actual_before_bars"] == 50
    assert result["actual_after_bars"] == 20
    timestamps = pd.to_datetime([bar["timestamp"] for bar in result["bars"]], utc=True)
    assert (timestamps < pd.Timestamp("2026-01-05T14:35:00Z")).sum() == 50
    assert (timestamps > pd.Timestamp("2026-01-05T14:50:00Z")).sum() == 20
    assert timestamps.min() < pd.Timestamp("2026-01-05T14:30:00Z")


def test_audit_context_allows_zero_after_bars():
    rows = regular_session("2026-01-05")
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    service = BacktestService(FakeMarketData(frame))

    result = service.audit_bars(
        symbol="AAPL",
        timeframe="5m",
        session="regular",
        entry=datetime(2026, 1, 5, 16, 0, tzinfo=timezone.utc),
        exit=datetime(2026, 1, 5, 16, 15, tzinfo=timezone.utc),
        before_bars=10,
        after_bars=0,
    )

    assert result["actual_before_bars"] == 10
    assert result["actual_after_bars"] == 0
