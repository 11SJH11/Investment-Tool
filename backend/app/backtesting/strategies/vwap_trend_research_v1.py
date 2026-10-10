"""VWAP Trend — Ledger research v1.

Research basis
--------------
Zarattini & Aziz, "Volume Weighted Average Price (VWAP): The Holy Grail for Day
Trading Systems", SSRN 4631351.

Rules represented here:
- QQQ/other US equity, 1-minute RTH bars.
- Session VWAP resets at 09:30.
- VWAP = cumulative HLC3*volume / cumulative volume.
- Desired position is long when completed 1-minute close > VWAP, short when close
  < VWAP.
- Reverse on each cross.
- Flat at the close.

Current Ledger limitation
-------------------------
Ledger cannot atomically close one side and open the opposite side at the same
next-bar open. On a cross while positioned, this strategy exits at the next open
and enters the new side one minute later. It also requires a stop on EntrySignal,
while the paper rule is cross-based; a very wide engine-only stop is therefore
used. These differences mean this is a near-replication until the engine gains
atomic reversal + stopless entry support.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo
import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "vwap_trend_research_v1"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "min_minutes_after_open": 1,
    "engine_safety_stop_pct": 90.0,
}


def _today_rth(frame):
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    ts = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert(NY)
    mins = ts.dt.hour * 60 + ts.dt.minute
    mask = (mins >= 570) & (mins < 960)
    out = out.loc[mask].copy()
    ts = ts.loc[mask]
    out["_date"] = ts.dt.date.values
    if out.empty:
        return out
    day = out.iloc[-1]["_date"]
    return out.loc[out["_date"] == day].reset_index(drop=True)


def _vwap(frame):
    volume = frame["volume"].astype(float)
    total = float(volume.sum())
    if total <= 0:
        return None
    tp = (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0
    return float((tp * volume).sum() / total)


def _safety_stop(reference, direction, pct):
    f = pct / 100.0
    return max(1e-9, reference * (1 - f)) if direction == "long" else reference * (1 + f)


@strategy_registry.register
class VwapTrendResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="VWAP Trend · research v1",
        description=(
            "Paper-style 1m VWAP trend: long above session HLC3 VWAP, short below, "
            "reverse on crosses, flat at close."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research",
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("min_minutes_after_open", "Earliest signal · minutes after 09:30", "int", 1, 1, 120, 1),
            ParameterSpec("engine_safety_stop_pct", "Engine-only catastrophic stop · %", "float", 90.0, 20.0, 99.0, 1.0),
        ),
        risk_management={
            "Entry/position": "Long above completed-bar session VWAP; short below.",
            "Reversal": "Exit on opposite cross, then current Ledger re-enters one minute later.",
            "Session": "Force flat at 16:00 via BacktestConfig allow_overnight=False.",
            "Stop": "No paper stop; wide engine-only stop is required by current Ledger.",
        },
        source_file="backend/app/backtesting/strategies/vwap_trend_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown VWAP trend parameter")
        super().__init__(**params)
        self._pending_reverse = None

    def reset(self):
        self._pending_reverse = None

    def _entry(self, ctx, side, vwap_value=None):
        reference = float(ctx.current_bar["close"])
        return EntrySignal(
            direction=side,
            stop_loss=_safety_stop(reference, side, float(self.params["engine_safety_stop_pct"])),
            take_profit=None,
            reason="vwap_trend",
            metadata={
                "paper": "Zarattini_Aziz_VWAP_4631351",
                "vwap": vwap_value,
                "direction": side,
                "paper_has_no_stop": True,
            },
        )

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("VWAP trend v1 requires primary timeframe 1m")

        if ctx.position is None and self._pending_reverse is not None:
            side = self._pending_reverse
            self._pending_reverse = None
            return self._entry(ctx, side, None)

        today = _today_rth(ctx.bars("1m", count=500))
        if today.empty:
            return None

        ts = pd.Timestamp(today.iloc[-1]["timestamp"])
        ts = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)
        minute_number = ts.hour * 60 + ts.minute - 570 + 1
        if minute_number < int(self.params["min_minutes_after_open"]):
            return None

        vwap_value = _vwap(today)
        if vwap_value is None:
            return None
        close = float(today.iloc[-1]["close"])
        desired = "long" if close > vwap_value else "short" if close < vwap_value else None

        allowed = str(self.params["direction"])
        if desired is not None and allowed != "both" and desired != allowed:
            desired = None

        if ctx.position is not None:
            if desired is None or desired == ctx.position.direction:
                return None
            self._pending_reverse = desired
            return ExitSignal("vwap_cross_reverse")

        if desired is None:
            return None
        return self._entry(ctx, desired, vwap_value)
