"""VWAP Trend with consecutive-close confirmation — Ledger research v2 (fixed).

This is a minimal, stateful extension of the already-working VWAP Trend v1.

Rules
-----
- 1-minute regular-session bars.
- Session VWAP resets at 09:30 ET and uses cumulative HLC3 * volume / volume.
- Each completed bar is classified:
    long-side  if close > current causal VWAP
    short-side if close < current causal VWAP
- Require N consecutive completed bars on the same side before opening or
  reversing. Default N=2.
- `confirmation_bars=1` approximates the original v1 signal behaviour.
- Flat at the close via Ledger run configuration.

Why this implementation is deliberately simple
-----------------------------------------------
The previous v2 recalculated a full per-bar VWAP series on every timestamp. This
version reuses the exact session-VWAP calculation path from the working v1 and
only adds a small causal streak state. That makes the research change isolated:
the only intended difference from v1 is the consecutive-close requirement.

Ledger limitation
-----------------
Ledger cannot atomically close and reverse at the same next-bar open. After an
opposite side obtains full N-bar confirmation, this strategy exits at the next
open and enters the already-confirmed opposite side on the following next-bar
opportunity. This is the same limitation as v1.

The source strategy has no protective stop. Ledger currently requires one, so a
very wide engine-only stop is used. For this strategy use position-value sizing,
not risk-based sizing.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo
import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "vwap_trend_confirmation_research_v2"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "confirmation_bars": 2,
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

    tp = (
        frame["high"].astype(float)
        + frame["low"].astype(float)
        + frame["close"].astype(float)
    ) / 3.0
    return float((tp * volume).sum() / total)


def _safety_stop(reference, direction, pct):
    f = float(pct) / 100.0
    if direction == "long":
        return max(1e-9, float(reference) * (1.0 - f))
    return float(reference) * (1.0 + f)


@strategy_registry.register
class VwapTrendConfirmationResearchV2(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="VWAP Trend Confirmation · research v2",
        description=(
            "VWAP Trend v1 plus one isolated change: require N consecutive "
            "completed closes on the same side of causal session VWAP."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research · refinement",
        parameters=(
            ParameterSpec(
                "direction",
                "Direction",
                "choice",
                "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "confirmation_bars",
                "Consecutive closes for confirmation",
                "int",
                2,
                1,
                10,
                1,
                help="Test 1 as control, then 2 and 3. No other signal filter changes.",
            ),
            ParameterSpec(
                "min_minutes_after_open",
                "Earliest signal · minutes after 09:30",
                "int",
                1,
                1,
                120,
                1,
            ),
            ParameterSpec(
                "engine_safety_stop_pct",
                "Engine-only catastrophic stop · %",
                "float",
                90.0,
                20.0,
                99.0,
                1.0,
                help="Not a paper stop. Use position-value sizing.",
            ),
        ),
        risk_management={
            "Signal": "N consecutive completed closes on one side of current causal session VWAP.",
            "Reversal": "Only after N consecutive completed closes on the opposite side.",
            "Session": "Force flat at 16:00 via BacktestConfig allow_overnight=False.",
            "Stop": "No paper stop; wide engine-only stop required by current Ledger.",
        },
        source_file="backend/app/backtesting/strategies/vwap_trend_confirmation_research_v2.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown VWAP confirmation parameter")
        super().__init__(**params)

        if str(self.params["direction"]) not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")

        self.params["confirmation_bars"] = int(self.params["confirmation_bars"])
        self.params["min_minutes_after_open"] = int(self.params["min_minutes_after_open"])
        self.params["engine_safety_stop_pct"] = float(self.params["engine_safety_stop_pct"])

        if self.params["confirmation_bars"] < 1:
            raise ValueError("confirmation_bars must be >= 1")
        if self.params["min_minutes_after_open"] < 1:
            raise ValueError("min_minutes_after_open must be >= 1")
        if not 0 < self.params["engine_safety_stop_pct"] < 100:
            raise ValueError("engine_safety_stop_pct must be between 0 and 100")

        self.reset()

    def reset(self):
        self._session_date = None
        self._streak_side = None
        self._streak_count = 0
        self._pending_reverse = None

    def _update_streak(self, side):
        if side is None:
            self._streak_side = None
            self._streak_count = 0
            return

        if side == self._streak_side:
            self._streak_count += 1
        else:
            self._streak_side = side
            self._streak_count = 1

    def _entry(self, ctx, side, vwap_value):
        reference = float(ctx.current_bar["close"])
        return EntrySignal(
            direction=side,
            stop_loss=_safety_stop(
                reference,
                side,
                float(self.params["engine_safety_stop_pct"]),
            ),
            take_profit=None,
            reason="vwap_trend_confirmed",
            metadata={
                "research_variant": "vwap_trend_confirmation_v2",
                "source_paper": "Zarattini_Aziz_VWAP_4631351",
                "vwap": float(vwap_value),
                "direction": side,
                "confirmation_bars": int(self.params["confirmation_bars"]),
                "confirmation_count": int(self._streak_count),
                "paper_has_no_stop": True,
            },
        )

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("VWAP trend confirmation v2 requires primary timeframe 1m")

        # Preserve the working v1 delayed-reversal behaviour.
        if ctx.position is None and self._pending_reverse is not None:
            side = self._pending_reverse
            self._pending_reverse = None

            today = _today_rth(ctx.bars("1m", count=500))
            if today.empty:
                return None
            vwap_value = _vwap(today)
            if vwap_value is None:
                return None
            return self._entry(ctx, side, vwap_value)

        today = _today_rth(ctx.bars("1m", count=500))
        if today.empty:
            return None

        current = today.iloc[-1]
        ts = pd.Timestamp(current["timestamp"])
        ts = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)

        session_date = ts.date()
        if session_date != self._session_date:
            self._session_date = session_date
            self._streak_side = None
            self._streak_count = 0
            self._pending_reverse = None

        minute_number = ts.hour * 60 + ts.minute - 570 + 1
        if minute_number < int(self.params["min_minutes_after_open"]):
            return None

        vwap_value = _vwap(today)
        if vwap_value is None:
            return None

        close = float(current["close"])
        raw_side = (
            "long" if close > vwap_value
            else "short" if close < vwap_value
            else None
        )

        allowed = str(self.params["direction"])
        if raw_side is not None and allowed != "both" and raw_side != allowed:
            raw_side = None

        self._update_streak(raw_side)

        required = int(self.params["confirmation_bars"])
        desired = (
            self._streak_side
            if self._streak_side is not None and self._streak_count >= required
            else None
        )

        if ctx.position is not None:
            if desired is None or desired == ctx.position.direction:
                return None

            self._pending_reverse = desired
            return ExitSignal("vwap_confirmed_reverse")

        if desired is None:
            return None

        return self._entry(ctx, desired, vwap_value)
