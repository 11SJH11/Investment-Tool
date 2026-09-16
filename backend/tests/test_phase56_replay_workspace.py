from types import SimpleNamespace

import pandas as pd

from app.services.backtest import BacktestService


class FakeMarketData:
    def __init__(self, frame):
        self.frame = frame
        self.provider = SimpleNamespace(historical_delay_minutes=0, historical_feed="sip", adjustment="split")

    def get_bars(self, symbol, timeframe, start, end):
        frame = self.frame.copy()
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        return frame[(ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))].reset_index(drop=True)


def multi_day_frame():
    rows = []
    for day_i, day in enumerate(("2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04")):
        start = pd.Timestamp(f"{day}T13:30:00Z")  # 09:30 EDT
        for i in range(78):
            ts = start + pd.Timedelta(minutes=5 * i)
            price = 100 + day_i * 2 + i * .02
            rows.append([ts, price, price + .2, price - .2, price + .05, 1000 + i])
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def test_replay_can_continue_across_multiple_sessions():
    service = BacktestService(FakeMarketData(multi_day_frame()))
    replay = service.replay_bars(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(),
        replay_end_date=pd.Timestamp("2026-06-04").date(),
        start_time="09:30", context_bars=5,
    )
    assert replay["replay_session_dates"] == ["2026-06-02", "2026-06-03", "2026-06-04"]
    future = replay["timeline"][replay["initial_visible_count"]:]
    assert any(stamp.startswith("2026-06-03") for stamp in future)
    assert any(stamp.startswith("2026-06-04") for stamp in future)
    assert all(pd.Timestamp(row["timestamp"]) <= pd.Timestamp(replay["frontier"]) for row in replay["bars"])


def test_replay_calendar_context_can_span_prior_days():
    service = BacktestService(FakeMarketData(multi_day_frame()))
    replay = service.replay_bars(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-03").date(),
        replay_end_date=pd.Timestamp("2026-06-04").date(),
        start_time="09:30", context_bars=0, context_days=2,
    )
    visible = replay["bars"][:replay["initial_visible_count"]]
    assert replay["context_days"] == 2
    assert any(str(row["timestamp"]).startswith("2026-06-01") for row in visible)
    assert any(str(row["timestamp"]).startswith("2026-06-02") for row in visible)


def test_replay_indicator_accepts_generic_indicator_parameters():
    service = BacktestService(FakeMarketData(multi_day_frame()))
    result = service.replay_indicator(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(),
        replay_end_date=pd.Timestamp("2026-06-03").date(),
        start_time="09:30", context_bars=30, key="bb_upper",
        params={"length": 10, "stddev": 1.5, "source": "close"},
    )
    assert result["params"]["length"] == 10
    assert result["params"]["stddev"] == 1.5
    assert result["overlay"] is True
    assert result["values"]


def test_replay_weekend_start_advances_to_next_available_session():
    service = BacktestService(FakeMarketData(multi_day_frame()))
    # 2026-05-31 is Sunday; the fixture's first available session is Monday 1 June.
    replay = service.replay_bars(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-05-31").date(),
        replay_end_date=pd.Timestamp("2026-06-02").date(),
        start_time="09:30", context_bars=0, context_days=1,
    )
    assert replay["requested_replay_date"] == "2026-05-31"
    assert replay["replay_date"] == "2026-06-01"
    assert replay["initial_visible_count"] >= 1
