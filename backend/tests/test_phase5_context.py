from datetime import datetime, timezone

import pandas as pd

from app.backtesting.context import StrategyContext


def test_context_hides_unfinished_higher_timeframe_bar():
    frames = {
        "5m": pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-02T14:30:00Z", "2026-01-02T14:35:00Z"]),
            "open": [100, 101], "high": [102, 103], "low": [99, 100], "close": [101, 102], "volume": [10, 10],
        }),
        "15m": pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-02T14:30:00Z", "2026-01-02T14:45:00Z"]),
            "open": [100, 103], "high": [104, 106], "low": [99, 102], "close": [103, 105], "volume": [30, 30],
        }),
    }
    ctx = StrategyContext(
        symbol="AAPL", primary_timeframe="5m",
        decision_time=datetime(2026, 1, 2, 14, 40, tzinfo=timezone.utc),
        frames=frames, position=None, equity=10_000,
    )
    assert len(ctx.bars("5m")) == 2
    assert len(ctx.bars("15m")) == 0

    later = StrategyContext(
        symbol="AAPL", primary_timeframe="5m",
        decision_time=datetime(2026, 1, 2, 14, 45, tzinfo=timezone.utc),
        frames=frames, position=None, equity=10_000,
    )
    assert len(later.bars("15m")) == 1
