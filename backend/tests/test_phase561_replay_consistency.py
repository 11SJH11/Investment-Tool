from types import SimpleNamespace

import pandas as pd

from app.indicators import indicator_registry
from app.services.backtest import BacktestService
from app.services.chart_data import prepare_chart_bars


class RecordingMarketData:
    def __init__(self, frame):
        self.frame = frame
        self.calls = []
        self.provider = SimpleNamespace(
            historical_delay_minutes=0,
            historical_feed="sip",
            adjustment="split",
        )

    def get_bars(self, symbol, timeframe, start, end):
        self.calls.append(timeframe)
        frame = self.frame.copy()
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        return frame[(ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))].reset_index(drop=True)


def minute_frame(day="2026-06-02"):
    start = pd.Timestamp(f"{day}T13:30:00Z")  # 09:30 EDT
    rows = []
    for i in range(390):
        ts = start + pd.Timedelta(minutes=i)
        price = 100 + i * 0.01
        rows.append([ts, price, price + 0.2, price - 0.2, price + 0.05, 100 + i])
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def test_replay_uses_one_minute_as_canonical_intraday_source():
    market = RecordingMarketData(minute_frame())
    service = BacktestService(market)
    replay = service.replay_bars(
        symbol="AAPL",
        timeframe="5m",
        session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(),
        replay_end_date=pd.Timestamp("2026-06-02").date(),
        start_time="10:00",
        context_bars=3,
    )
    assert market.calls and set(market.calls) == {"1m"}
    assert replay["source_timeframe"] == "1m"
    assert replay["aggregation"] == "replay_causal_aligned_from_1m"
    times = pd.to_datetime([row["timestamp"] for row in replay["bars"]], utc=True)
    assert all(delta.total_seconds() == 300 for delta in times.to_series().diff().dropna())


def test_replay_1m_and_5m_are_derived_from_same_minute_series():
    frame = minute_frame()
    market = RecordingMarketData(frame)
    service = BacktestService(market)
    one = service.replay_bars(
        symbol="AAPL", timeframe="1m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(), replay_end_date=pd.Timestamp("2026-06-02").date(),
        start_time="10:00", context_bars=5,
    )
    five = service.replay_bars(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(), replay_end_date=pd.Timestamp("2026-06-02").date(),
        start_time="10:00", context_bars=5,
    )
    assert one["source_timeframe"] == five["source_timeframe"] == "1m"
    one_by_time = {str(pd.Timestamp(row["timestamp"]).floor("min")): row for row in one["bars"]}
    target_five = next(row for row in five["bars"] if pd.Timestamp(row["timestamp"]) == pd.Timestamp("2026-06-02T14:00:00Z"))
    start = pd.Timestamp(target_five["timestamp"])
    # At 10:00 only the first canonical minute of the 10:00 bucket is revealed.
    minute_rows = [one_by_time[str(start.floor("min"))]]
    assert target_five["is_partial"] is True
    assert target_five["open"] == minute_rows[0]["open"]
    assert target_five["close"] == minute_rows[-1]["close"]
    assert target_five["high"] == max(row["high"] for row in minute_rows)
    assert target_five["low"] == min(row["low"] for row in minute_rows)
    assert target_five["volume"] == sum(row["volume"] for row in minute_rows)


def test_prepare_chart_bars_preserves_provider_native_cadence_when_already_matching():
    start = pd.Timestamp("2026-06-02T13:30:00Z")
    rows = []
    for i in range(4):
        ts = start + pd.Timedelta(minutes=5 * i)
        rows.append([ts, 100 + i, 101 + i, 99 + i, 100.5 + i, 1000])
    frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    out, mode = prepare_chart_bars(frame, "5m", "regular")
    assert len(out) == len(frame)
    assert mode == "session_filtered"


def test_volume_is_registered_as_shared_indicator():
    indicator = indicator_registry.create("volume")
    frame = minute_frame().head(3)
    result = indicator.calculate(frame)
    assert indicator.spec.overlay is False
    assert result.tolist() == frame["volume"].astype(float).tolist()
