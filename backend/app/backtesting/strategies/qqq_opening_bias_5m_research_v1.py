"""Zarattini-Aziz QQQ 5-minute opening-bias / ORB — Ledger research v1.

Research basis
--------------
Zarattini & Aziz, "Can Day Trading Really Be Profitable?", SSRN 4416622.

Paper-style defaults represented here:
- QQQ, 5-minute RTH bars.
- Inspect the first 09:30-09:35 candle.
- Bullish first candle -> long at the OPEN of the second 5-minute candle.
- Bearish first candle -> short at the OPEN of the second 5-minute candle.
- Stop at the opposite extreme of the first candle.
- Profit target = configurable fixed R; paper-style default remains 10R.
- Otherwise flatten at the close.
- Paper/account settings such as 1% risk and leverage cap belong in Ledger's
  BacktestConfig, not this strategy.

This strategy maps cleanly to Ledger's causal contract: the signal is created
when the first 5-minute candle completes and Ledger fills at the next 5-minute
bar open.

2026-10-01 change:
- `target_r` is now an ORDINARY strategy parameter rather than a hidden research
  parameter, so the Strategy Lab UI can directly run 2R/3R/4R/5R/10R tests.
- Signal, stop, session and entry rules are unchanged.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo
import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "qqq_opening_bias_5m_research_v1"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "target_r": 10.0,
    "doji_body_threshold_pct": 0.0,
}


@strategy_registry.register
class QqqOpeningBias5mResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="QQQ 5m Opening Bias / ORB · research v1",
        description=(
            "First-5m directional strategy: second-bar-open entry, first-bar "
            "opposite extreme stop, configurable fixed-R target or session close."
        ),
        defaults=DEFAULTS,
        timeframes=("5m",),
        category="Published research",
        parameters=(
            ParameterSpec(
                "direction",
                "Direction",
                "choice",
                "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "target_r",
                "Target R",
                "float",
                10.0,
                1.0,
                20.0,
                0.5,
                help=(
                    "Paper-style default is 10R. Change this directly for modern "
                    "target sensitivity tests while leaving entry/stop logic frozen."
                ),
            ),
            ParameterSpec(
                "doji_body_threshold_pct",
                "Minimum first-candle body · % of open",
                "float",
                0.0,
                0.0,
                2.0,
                0.01,
                help=(
                    "0 matches the sign-only paper-style baseline; positive values "
                    "are separate research variants."
                ),
            ),
        ),
        risk_management={
            "Entry": "At 09:35 next-bar open, in the direction of the first 5-minute candle.",
            "Stop": "Opposite extreme of the first 5-minute candle.",
            "Target": "Configurable fixed R; 10R paper-style default.",
            "Session": "Force flat at 16:00 via BacktestConfig allow_overnight=False.",
        },
        source_file="backend/app/backtesting/strategies/qqq_opening_bias_5m_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown QQQ opening-bias parameter")
        super().__init__(**params)

        if str(self.params["direction"]) not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")

        target_r = float(self.params["target_r"])
        if not target_r > 0:
            raise ValueError("target_r must be positive")
        self.params["target_r"] = target_r

        threshold = float(self.params["doji_body_threshold_pct"])
        if threshold < 0:
            raise ValueError("doji_body_threshold_pct cannot be negative")
        self.params["doji_body_threshold_pct"] = threshold

        self._used_dates = set()

    def reset(self):
        self._used_dates = set()

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "5m":
            raise ValueError("QQQ opening-bias v1 requires primary timeframe 5m")
        if ctx.position is not None:
            return None

        bars = ctx.bars("5m", count=3)
        if bars is None or bars.empty:
            return None

        current = bars.iloc[-1]
        ts = pd.Timestamp(current["timestamp"])
        ts = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)

        # First RTH 5-minute candle starts at 09:30 and is complete at 09:35.
        if not (ts.hour == 9 and ts.minute == 30):
            return None

        day = ts.date()
        if day in self._used_dates:
            return None

        op = float(current["open"])
        cl = float(current["close"])
        hi = float(current["high"])
        lo = float(current["low"])
        if op <= 0 or hi <= lo:
            self._used_dates.add(day)
            return None

        body_pct = abs(cl - op) / op * 100.0
        threshold = float(self.params["doji_body_threshold_pct"])
        if body_pct <= threshold:
            self._used_dates.add(day)
            return None

        side = "long" if cl > op else "short" if cl < op else None
        if side is None:
            self._used_dates.add(day)
            return None

        allowed = str(self.params["direction"])
        if allowed != "both" and side != allowed:
            self._used_dates.add(day)
            return None

        stop = lo if side == "long" else hi
        target_r = float(self.params["target_r"])
        self._used_dates.add(day)

        return EntrySignal(
            direction=side,
            stop_loss=stop,
            take_profit=None,
            target_r=target_r,
            reason="qqq_first_5m_direction",
            metadata={
                "paper": "Zarattini_Aziz_ORB_4416622",
                "session_date": str(day),
                "first_bar_open": op,
                "first_bar_high": hi,
                "first_bar_low": lo,
                "first_bar_close": cl,
                "first_bar_body_pct": body_pct,
                "target_r": target_r,
            },
        )
