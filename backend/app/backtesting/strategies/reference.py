from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.context import StrategyContext
from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

NY = ZoneInfo("America/New_York")


@strategy_registry.register
class EmaCrossReference(Strategy):
    """Reference strategy used to verify the engine/indicator plugin path.

    It is intentionally simple and is not presented as a recommended trading edge.
    """

    spec = StrategySpec(
        key="ema_cross_reference",
        name="EMA Cross · reference",
        description="Engine reference: EMA cross with strategy-owned ATR stop and 2R target. Signals are evaluated at bar close and filled at the next bar open.",
        category="Engine reference",
        defaults={"fast_length": 10, "slow_length": 30, "atr_length": 14, "direction": "both"},
        timeframes=("5m",),
        parameters=(
            ParameterSpec("fast_length", "Fast EMA", "int", 10, 2, 200, 1),
            ParameterSpec("slow_length", "Slow EMA", "int", 30, 3, 400, 1),
            ParameterSpec("atr_length", "ATR length", "int", 14, 2, 100, 1),
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
        ),
        research_parameters=(
            ParameterSpec("stop_atr", "Stop distance · ATR", "float", 1.5, 0.25, 10.0, 0.25, help="Research-only override; normal runs use the strategy-owned default."),
            ParameterSpec("target_rr", "Target R:R", "float", 2.0, 0.25, 10.0, 0.25, help="Research-only override; normal runs use the strategy-owned default."),
        ),
        risk_management={
            "Initial stop": "1.5 × ATR(14) from the signal close",
            "Initial target": "2.0R from the initial stop distance",
            "Breakeven": "Off in this reference strategy",
            "Partial exits": "Off in this reference strategy",
            "Trailing stop": "Off in this reference strategy",
        },
        source_file="backend/app/backtesting/strategies/reference.py",
    )

    # Strategy-owned risk management. These are deliberately code-level rules,
    # not generic per-run fields. A real strategy plugin can use completely
    # different stop/target/management logic.
    STOP_ATR = 1.5
    TARGET_RR = 2.0
    BREAKEVEN_TRIGGER_R = 0.0
    PARTIAL_TRIGGER_R = 0.0
    PARTIAL_FRACTION = 0.5
    TRAIL_ATR_MULTIPLE = 0.0

    def on_bar(self, ctx: StrategyContext):
        bars = ctx.bars(count=max(int(self.params["slow_length"]), int(self.params["atr_length"])) + 3)
        if len(bars) < int(self.params["slow_length"]) + 2:
            return None
        fast = ctx.indicator("ema", length=int(self.params["fast_length"]))
        slow = ctx.indicator("ema", length=int(self.params["slow_length"]))
        atr = ctx.indicator("atr", length=int(self.params["atr_length"]))
        if len(fast) < 2 or len(slow) < 2 or pd.isna(atr.iloc[-1]):
            return None

        crossed_up = fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]
        crossed_down = fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]
        direction = str(self.params["direction"])

        if ctx.position is not None:
            if ctx.position.direction == "long" and crossed_down:
                return ExitSignal("opposite_ema_cross")
            if ctx.position.direction == "short" and crossed_up:
                return ExitSignal("opposite_ema_cross")

            position = ctx.position
            close = float(ctx.current_bar["close"])
            risk_per_share = max(float(position.initial_risk_per_share), 1e-12)
            multiplier = 1.0 if position.direction == "long" else -1.0
            open_r = (close - float(position.entry_price)) * multiplier / risk_per_share
            new_stop = None
            reduce_fraction = None
            management_meta = {}

            breakeven_trigger = float(self.BREAKEVEN_TRIGGER_R)
            if breakeven_trigger > 0 and open_r >= breakeven_trigger and not position.metadata.get("breakeven_applied"):
                candidate = float(position.entry_price)
                if (position.direction == "long" and candidate > position.stop_loss) or (position.direction == "short" and candidate < position.stop_loss):
                    new_stop = candidate
                management_meta["breakeven_applied"] = True

            partial_trigger = float(self.PARTIAL_TRIGGER_R)
            if partial_trigger > 0 and open_r >= partial_trigger and not position.metadata.get("partial_exit_applied"):
                reduce_fraction = float(self.PARTIAL_FRACTION)
                management_meta["partial_exit_applied"] = True

            trail_multiple = float(self.TRAIL_ATR_MULTIPLE)
            if trail_multiple > 0 and not pd.isna(atr.iloc[-1]):
                distance = float(atr.iloc[-1]) * trail_multiple
                candidate = close - distance if position.direction == "long" else close + distance
                current = float(position.stop_loss if new_stop is None else new_stop)
                if (position.direction == "long" and candidate > current) or (position.direction == "short" and candidate < current):
                    new_stop = candidate
                    management_meta["trailing_stop_active"] = True
                    management_meta["trailing_atr_multiple"] = trail_multiple

            if new_stop is not None or reduce_fraction is not None or management_meta:
                management_meta["management_open_r"] = open_r
                return ManagePositionSignal(
                    new_stop_loss=new_stop, reduce_fraction=reduce_fraction,
                    reason="ema_reference_management", metadata=management_meta,
                )
            return None

        close = float(ctx.current_bar["close"])
        risk = float(atr.iloc[-1]) * float(self.params.get("stop_atr", self.STOP_ATR))
        if not risk > 0:
            return None
        rr = float(self.params.get("target_rr", self.TARGET_RR))
        signal_metadata = {
            "signal_close": close,
            "fast_ema": float(fast.iloc[-1]),
            "slow_ema": float(slow.iloc[-1]),
            "fast_ema_previous": float(fast.iloc[-2]),
            "slow_ema_previous": float(slow.iloc[-2]),
            "atr": float(atr.iloc[-1]),
            "fast_length": int(self.params["fast_length"]),
            "slow_length": int(self.params["slow_length"]),
            "atr_length": int(self.params["atr_length"]),
            "stop_atr": float(self.params.get("stop_atr", self.STOP_ATR)),
            "target_rr": rr,
        }
        if crossed_up and direction in {"both", "long"}:
            return EntrySignal(
                "long", stop_loss=close - risk, take_profit=close + risk * rr,
                reason="bullish_ema_cross", metadata=signal_metadata,
            )
        if crossed_down and direction in {"both", "short"}:
            return EntrySignal(
                "short", stop_loss=close + risk, take_profit=close - risk * rr,
                reason="bearish_ema_cross", metadata=signal_metadata,
            )
        return None


@strategy_registry.register
class OpeningRangeBreakoutReference(Strategy):
    spec = StrategySpec(
        key="opening_range_breakout_reference",
        name="Opening Range Breakout · reference",
        description="Reference NY-session breakout. Builds the opening range from completed bars, then enters the first close outside it. Stop is the opposite side of the range.",
        category="Engine reference",
        defaults={"range_minutes": 30, "direction": "both", "latest_entry_minute": 180},
        timeframes=("5m",),
        parameters=(
            ParameterSpec("range_minutes", "Opening range minutes", "choice", "30", choices=("15", "30", "60")),
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("latest_entry_minute", "Latest entry · minutes after open", "int", 180, 30, 390, 5),
        ),
        research_parameters=(
            ParameterSpec("target_rr", "Target R:R", "float", 2.0, 0.25, 10.0, 0.25, help="Research-only override; normal runs use the strategy-owned default."),
        ),
        risk_management={
            "Initial stop": "Opposite side of the completed opening range",
            "Initial target": "2.0R from the breakout entry logic",
            "Breakeven / partials / trailing": "None in this reference strategy",
        },
        source_file="backend/app/backtesting/strategies/reference.py",
    )

    TARGET_RR = 2.0

    def __init__(self, **params):
        super().__init__(**params)
        self._traded_dates: set[object] = set()

    def reset(self) -> None:
        self._traded_dates.clear()

    def on_bar(self, ctx: StrategyContext):
        if ctx.position is not None:
            return None
        bars = ctx.bars()
        if bars.empty:
            return None
        local = pd.to_datetime(bars["timestamp"], utc=True).dt.tz_convert(NY)
        now = local.iloc[-1]
        session_date = now.date()
        if session_date in self._traded_dates:
            return None
        minutes_from_open = (now.hour * 60 + now.minute) - (9 * 60 + 30)
        range_minutes = int(self.params["range_minutes"])
        if minutes_from_open < range_minutes or minutes_from_open > int(self.params["latest_entry_minute"]):
            return None

        today = bars[local.dt.date == session_date].copy()
        today_local = pd.to_datetime(today["timestamp"], utc=True).dt.tz_convert(NY)
        open_minutes = today_local.dt.hour * 60 + today_local.dt.minute
        opening = today[(open_minutes >= 570) & (open_minutes < 570 + range_minutes)]
        if opening.empty:
            return None
        range_high = float(opening["high"].max())
        range_low = float(opening["low"].min())
        close = float(today.iloc[-1]["close"])
        width = range_high - range_low
        if width <= 0:
            return None
        rr = float(self.params.get("target_rr", self.TARGET_RR))
        direction = str(self.params["direction"])

        metadata = {
            "signal_close": close,
            "opening_range_high": range_high,
            "opening_range_low": range_low,
            "opening_range_width": width,
            "range_minutes": range_minutes,
            "minutes_from_open": int(minutes_from_open),
            "target_rr": rr,
        }
        if close > range_high and direction in {"both", "long"}:
            self._traded_dates.add(session_date)
            return EntrySignal(
                "long", stop_loss=range_low, take_profit=close + (close - range_low) * rr,
                reason="opening_range_breakout", metadata=metadata,
            )
        if close < range_low and direction in {"both", "short"}:
            self._traded_dates.add(session_date)
            return EntrySignal(
                "short", stop_loss=range_high, take_profit=close - (range_high - close) * rr,
                reason="opening_range_breakdown", metadata=metadata,
            )
        return None
