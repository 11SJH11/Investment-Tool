"""Focused deterministic research checks. Run from Ledger's backend directory."""
from __future__ import annotations

from datetime import timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.experimental_strategy_batch_2026_v1 import DailyHourlyFiveMinNoBias
from app.backtesting.strategies.mtf_ict_research_v2 import (
    MTFV2ALongOnly, MTFV2CLevelProximity, ICTC03ThreeOfFive, ICTC04FourOfFive,
    ICTC05AllFive, _fib_retracement_zone, _recent_pivot, _three_candle_fvg,
)


class FakeContext:
    def __init__(self, five, hourly=None):
        self.five = five
        self.hourly = hourly if hourly is not None else five
        self.primary_timeframe = "5m"
        self.position = None
        self.current_bar = five.iloc[-1]
        last = pd.Timestamp(five.iloc[-1]["timestamp"])
        self.decision_time = last + pd.Timedelta(minutes=5)
        if self.decision_time.tzinfo is None:
            self.decision_time = self.decision_time.tz_localize("UTC")

    def bars(self, timeframe, count=None):
        frame = self.five if timeframe == "5m" else self.hourly
        return frame.tail(count).copy() if count else frame.copy()


def _candle(ts, o, h, l, c):
    assert l <= min(o, c) <= max(o, c) <= h
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 10}


def _completed_hourly():
    start = pd.Timestamp("2025-01-12T00:00:00Z")
    rows = []
    for i in range(36):
        # Exactly one well-confirmed 1h low at index 24 (100.0), then rising lows.
        lo = 103.0 + abs(i-24) * 0.06
        if i == 24:
            lo = 100.0
        rows.append(_candle(start + timedelta(hours=i), lo+0.8, lo+2.0, lo, lo+0.9))
    return pd.DataFrame(rows)


def _complete_5m_setup():
    # A 1h-confirmed low at 100 gets swept/reclaimed. Next 5m candle closes
    # above the previously confirmed 5m swing high; following candle pulls back
    # to the 50%-78.6% retracement and reverses upwards.
    start = pd.Timestamp("2025-01-13T10:00:00Z")
    rows = []
    for i in range(70):
        # Oscillating completed bars make a 2L/2R-confirmed 5m swing high.
        center = 102.4 + (0.6 if i % 8 == 2 else 0.0)
        rows.append(_candle(start + timedelta(minutes=5*i), center, center+0.5,
                            center-0.6, center+0.1))
    rows.append(_candle(start+timedelta(minutes=5*70), 101.4, 102.6, 99.5, 101.1))  # sweep/reclaim
    rows.append(_candle(start+timedelta(minutes=5*71), 101.2, 105.5, 100.8, 105.0))  # BOS
    rows.append(_candle(start+timedelta(minutes=5*72), 102.0, 103.0, 101.0, 102.6))  # fib reversal
    return pd.DataFrame(rows)


def test_registered_specs_and_reset():
    keys = [MTFV2ALongOnly, MTFV2CLevelProximity,
            ICTC03ThreeOfFive, ICTC04FourOfFive, ICTC05AllFive]
    assert len(set(cls.spec.key for cls in keys)) == 5
    for cls in keys:
        obj = cls()
        obj.reset()
        assert obj.spec.timeframes[0] == "5m"


def test_long_only_discards_short_setup_at_breakout(monkeypatch):
    base = DailyHourlyFiveMinNoBias
    def pretend(self, ctx):
        self.state = {"direction": "short"}
        return None
    monkeypatch.setattr(base, "on_bar", pretend)
    subject = MTFV2ALongOnly()
    assert subject.on_bar(object()) is None
    assert subject.state is None


def test_long_only_keeps_long_entry(monkeypatch):
    monkeypatch.setattr(DailyHourlyFiveMinNoBias, "on_bar", lambda self, ctx:
                        EntrySignal("long", stop_loss=100, target_r=2, metadata={"x": 1}))
    subject = MTFV2ALongOnly()
    out = subject.on_bar(object())
    assert out.direction == "long"
    assert out.metadata["research_variant"] == "MTF_V2A_long_only"


@pytest.mark.parametrize("close,expected", [(100.4, True), (101.5, False)])
def test_v2c_uses_completed_signal_close_not_future_fill(monkeypatch, close, expected):
    # Planned stop=99.5, level=100. For close=100.4: ratio=.4/.9 <.5;
    # for close=101.5: ratio=1.5/2 >.5.
    monkeypatch.setattr(DailyHourlyFiveMinNoBias, "on_bar", lambda self, ctx:
                        EntrySignal("long", stop_loss=99.5, target_r=2,
                                    metadata={"hourly_breakout_level": 100.0}))
    subject = MTFV2CLevelProximity()
    ctx = type("Ctx", (), {"current_bar": {"close": close}})()
    out = subject.on_bar(ctx)
    assert isinstance(out, EntrySignal) is expected
    if out:
        assert out.metadata["level_distance_r_at_signal"] <= 0.5


def test_confirmed_pivot_does_not_look_ahead():
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    highs = [2, 3, 5, 3, 2]
    data = pd.DataFrame([_candle(start+timedelta(hours=i), 1.5, h, 1.0, 1.8)
                         for i, h in enumerate(highs)])
    assert _recent_pivot(data.iloc[:4], "high") is None
    assert _recent_pivot(data, "high")["price"] == 5


def test_fvg_only_on_contiguous_completed_three_candles():
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    rows = [_candle(start, 100, 101, 99, 100),
            _candle(start+timedelta(minutes=5), 102, 103, 101, 102),
            _candle(start+timedelta(minutes=10), 104, 106, 102, 105)]
    gap = _three_candle_fvg(pd.DataFrame(rows))
    assert gap["direction"] == "long"
    assert (gap["lower"], gap["upper"]) == (101, 102)
    rows[-1]["timestamp"] += timedelta(minutes=10)
    assert _three_candle_fvg(pd.DataFrame(rows)) is None


def test_fib_band_is_mirrored_and_never_uses_future_bars():
    assert _fib_retracement_zone("long", 100, 110) == pytest.approx((102.14, 105))
    assert _fib_retracement_zone("short", 100, 110) == pytest.approx((105, 107.86))


def test_ict_three_step_entry_from_completed_bars():
    bars = _complete_5m_setup()
    hours = _completed_hourly()
    # Supply only the bars that are complete on each replay step.
    subject = ICTC03ThreeOfFive()
    last_out = None
    for i in range(35, len(bars)):
        ctx = FakeContext(bars.iloc[:i+1], hours)
        sig = subject.on_bar(ctx)
        if sig is not None:
            last_out = sig
    assert isinstance(last_out, EntrySignal)
    assert last_out.direction == "long"
    assert last_out.metadata["score"] >= 3
    assert last_out.metadata["flags"]["liquidity_sweep"] is True
    assert last_out.metadata["flags"]["confirmed_5m_bos"] is True
    assert last_out.metadata["flags"]["fib_50_786_retest"] is True
    assert last_out.stop_loss < last_out.metadata["signal_close"]


def test_stricter_threshold_does_not_create_trades_from_same_fixture():
    bars = _complete_5m_setup()
    hours = _completed_hourly()
    counts = {}
    for cls in (ICTC03ThreeOfFive, ICTC04FourOfFive, ICTC05AllFive):
        strategy = cls()
        signals = []
        for i in range(35, len(bars)):
            result = strategy.on_bar(FakeContext(bars.iloc[:i+1], hours))
            if isinstance(result, EntrySignal):
                signals.append(result)
        counts[cls.MIN_CONFLUENCES] = len(signals)
    assert counts[3] >= counts[4] >= counts[5]


def test_full_five_confluences_can_generate_a_valid_signal():
    bars = _complete_5m_setup()
    s = ICTC05AllFive()
    last = bars.iloc[-1]
    stamp = pd.Timestamp(last["timestamp"])
    s.state = {
        "stage": "BOS", "direction": "long", "sweep_at": stamp-pd.Timedelta(minutes=10),
        "last_at": stamp-pd.Timedelta(minutes=5), "stage_bars": 0,
        "liquidity": {"price": 100, "time": stamp-pd.Timedelta(hours=5)},
        "bos": {"price": 103, "time": stamp-pd.Timedelta(minutes=20)},
        "sweep_extreme": 99.5, "bos_at": stamp-pd.Timedelta(minutes=5),
        "impulse_low": 99.5, "impulse_high": 105.5,
        "fib": (100.78, 102.5),
        "ob": {"low": 101.0, "high": 102.4, "time": stamp-pd.Timedelta(minutes=10)},
        "gap_events": [{"direction": "long", "kind": "FVG",
                         "lower": 101.1, "upper": 102.2,
                         "time": stamp-pd.Timedelta(minutes=5)}],
    }
    out = s.on_bar(FakeContext(bars, _completed_hourly()))
    assert isinstance(out, EntrySignal)
    assert out.metadata["score"] == 5
    assert all(out.metadata["flags"].values())


def test_strict_candidate_is_consumed_after_scoring_failure():
    bars = _complete_5m_setup()
    s = ICTC05AllFive()
    # A naturally occurring 3-of-5 pattern is insufficient for strict mode.
    for i in range(35, len(bars)):
        assert s.on_bar(FakeContext(bars.iloc[:i+1], _completed_hourly())) is None
    assert len(s.used_days) >= 1
