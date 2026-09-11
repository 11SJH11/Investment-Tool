from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.context import StrategyContext
from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

TOKYO = ZoneInfo("Asia/Tokyo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


@strategy_registry.register
class XauLiquiditySweepType3Baseline(Strategy):
    """Mechanical baseline for the user's XAUUSD liquidity/Type-3 idea.

    The intentionally subjective phrase "relevant recent liquidity" is made
    reproducible here as the most recent *confirmed* 1H pivot high/low. Type-3
    structure is confirmed on completed 1m closes. Entry is a persistent 50%
    limit order rather than a next-open market approximation.
    """

    spec = StrategySpec(
        key="xau_liquidity_type3_baseline_v1",
        name="XAUUSD Liquidity Sweep + Type 3 + 50% · baseline v1.1",
        description=(
            "Baseline research strategy: most recent confirmed 1H pivot is the liquidity level; "
            "1m sweeps it, then a 1m close through a stronger opposing swing selected from the "
            "bounded pre-sweep structure confirms Type 3. A limit order waits at 50% of the "
            "confirmation impulse, stop at the structural sweep extreme, target 1.5R. Sessions "
            "are tagged only; they do not filter entries."
        ),
        category="Research baseline",
        defaults={
            "direction": "both",
            "liquidity_pivot_left": 2,
            "liquidity_pivot_right": 2,
            "execution_pivot_left": 2,
            "execution_pivot_right": 2,
            "structure_lookback_bars": 40,
            "minimum_structure_bars": 3,
            "max_type3_wait_bars": 120,
            "limit_wait_bars": 120,
            "entry_retrace": 0.5,
            "target_r": 1.5,
        },
        timeframes=("1m", "1h"),
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("liquidity_pivot_left", "1H pivot left bars", "int", 2, 1, 10, 1,
                          help="Mechanical definition of the higher-timeframe liquidity level."),
            ParameterSpec("liquidity_pivot_right", "1H pivot right bars", "int", 2, 1, 10, 1),
            ParameterSpec("execution_pivot_left", "1m swing left bars", "int", 2, 1, 10, 1),
            ParameterSpec("execution_pivot_right", "1m swing right bars", "int", 2, 1, 10, 1),
            ParameterSpec("structure_lookback_bars", "Type 3 structure lookback", "int", 40, 5, 240, 1,
                          help="Search this many completed 1m bars before the sweep/extreme for the stronger opposing swing."),
            ParameterSpec("minimum_structure_bars", "Minimum swing → sweep bars", "int", 3, 1, 60, 1,
                          help="Prevents a tiny pivot immediately beside the sweep from becoming the Type 3 level."),
            ParameterSpec("max_type3_wait_bars", "Max bars sweep → Type 3", "int", 120, 1, 1440, 1),
            ParameterSpec("limit_wait_bars", "Max bars waiting at 50%", "int", 120, 1, 1440, 1),
        ),
        research_parameters=(
            ParameterSpec("entry_retrace", "Entry retracement", "float", 0.5, 0.1, 0.9, 0.05,
                          help="Baseline is fixed at 50%; expose only for later sensitivity tests."),
            ParameterSpec("target_r", "Target R", "float", 1.5, 0.5, 5.0, 0.25,
                          help="Baseline is 1.5R; expose only for later sensitivity tests."),
        ),
        risk_management={
            "Liquidity": "Most recent confirmed 1H pivot high/low (2-left / 2-right by default)",
            "Confirmation": "1m candle CLOSE through stronger opposing swing from bounded pre-sweep structure",
            "Entry": "Persistent limit at 50% of confirmation impulse",
            "Stop": "Structural sweep / Type-3 extreme",
            "Target": "1.5R baseline",
            "Session": "Never filters baseline; setup is tagged Asia/London/New York/overlap",
            "Confluences": "None in v1.1; add independently in later experiments",
        },
        source_file="backend/app/backtesting/strategies/xau_liquidity_type3.py",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._state: dict | None = None

    def reset(self) -> None:
        self._state = None

    def on_bar(self, ctx: StrategyContext):
        if ctx.primary_timeframe != "1m":
            return None
        one = ctx.bars("1m")
        hourly = ctx.bars("1h")
        if len(one) < 8 or len(hourly) < 8 or ctx.position is not None:
            return None

        current = one.iloc[-1]
        current_time = _ts(current["timestamp"])
        direction = str(self.params["direction"])

        # Continue an already-detected sweep until Type-3 confirmation or expiry.
        if self._state is not None:
            state = self._state
            state["bars_waited"] += 1
            if state["bars_waited"] > int(self.params["max_type3_wait_bars"]):
                self._state = None
                return None

            if state["direction"] == "long":
                if float(current["low"]) < state["structural_extreme"]:
                    state["structural_extreme"] = float(current["low"])
                    state["structural_time"] = current_time
                swing = _strongest_pre_extreme_pivot(
                    one, "high", int(self.params["execution_pivot_left"]),
                    int(self.params["execution_pivot_right"]), before=state["structural_time"],
                    lookback_bars=int(self.params["structure_lookback_bars"]),
                    minimum_structure_bars=int(self.params["minimum_structure_bars"]),
                )
                if swing is not None:
                    state["break_level"] = float(swing["price"])
                    state["break_level_time"] = swing["time"]
                if state.get("break_level") is not None and float(current["close"]) > float(state["break_level"]):
                    return self._confirm(state, current, current_time)
            else:
                if float(current["high"]) > state["structural_extreme"]:
                    state["structural_extreme"] = float(current["high"])
                    state["structural_time"] = current_time
                swing = _strongest_pre_extreme_pivot(
                    one, "low", int(self.params["execution_pivot_left"]),
                    int(self.params["execution_pivot_right"]), before=state["structural_time"],
                    lookback_bars=int(self.params["structure_lookback_bars"]),
                    minimum_structure_bars=int(self.params["minimum_structure_bars"]),
                )
                if swing is not None:
                    state["break_level"] = float(swing["price"])
                    state["break_level_time"] = swing["time"]
                if state.get("break_level") is not None and float(current["close"]) < float(state["break_level"]):
                    return self._confirm(state, current, current_time)
            return None

        # A new baseline setup uses the newest confirmed 1H pivot on each side.
        low_level = _latest_confirmed_pivot(
            hourly, "low", int(self.params["liquidity_pivot_left"]), int(self.params["liquidity_pivot_right"])
        )
        high_level = _latest_confirmed_pivot(
            hourly, "high", int(self.params["liquidity_pivot_left"]), int(self.params["liquidity_pivot_right"])
        )
        swept_low = low_level is not None and float(current["low"]) < float(low_level["price"])
        swept_high = high_level is not None and float(current["high"]) > float(high_level["price"])
        # A single enormous candle sweeping both sides is ambiguous for this baseline.
        if swept_low and swept_high:
            return None

        if swept_low and direction in {"both", "long"}:
            swing = _strongest_pre_extreme_pivot(
                one, "high", int(self.params["execution_pivot_left"]), int(self.params["execution_pivot_right"]),
                before=current_time, lookback_bars=int(self.params["structure_lookback_bars"]),
                minimum_structure_bars=int(self.params["minimum_structure_bars"]),
            )
            self._state = {
                "direction": "long", "liquidity_price": float(low_level["price"]), "liquidity_time": low_level["time"],
                "sweep_time": current_time, "sweep_price": float(current["low"]),
                "structural_extreme": float(current["low"]), "structural_time": current_time,
                "break_level": float(swing["price"]) if swing else None,
                "break_level_time": swing["time"] if swing else None, "bars_waited": 0,
            }
        elif swept_high and direction in {"both", "short"}:
            swing = _strongest_pre_extreme_pivot(
                one, "low", int(self.params["execution_pivot_left"]), int(self.params["execution_pivot_right"]),
                before=current_time, lookback_bars=int(self.params["structure_lookback_bars"]),
                minimum_structure_bars=int(self.params["minimum_structure_bars"]),
            )
            self._state = {
                "direction": "short", "liquidity_price": float(high_level["price"]), "liquidity_time": high_level["time"],
                "sweep_time": current_time, "sweep_price": float(current["high"]),
                "structural_extreme": float(current["high"]), "structural_time": current_time,
                "break_level": float(swing["price"]) if swing else None,
                "break_level_time": swing["time"] if swing else None, "bars_waited": 0,
            }
        return None

    def _confirm(self, state: dict, current: pd.Series, confirmation_time: datetime) -> EntrySignal | None:
        retrace = float(self.params.get("entry_retrace", 0.5))
        target_r = float(self.params.get("target_r", 1.5))
        if state["direction"] == "long":
            impulse_low = float(state["structural_extreme"])
            impulse_high = float(current["high"])
            entry = impulse_low + (impulse_high - impulse_low) * retrace
            stop = impulse_low
            risk = entry - stop
            target = entry + risk * target_r
        else:
            impulse_high = float(state["structural_extreme"])
            impulse_low = float(current["low"])
            entry = impulse_high - (impulse_high - impulse_low) * retrace
            stop = impulse_high
            risk = stop - entry
            target = entry - risk * target_r
        self._state = None
        if risk <= 0:
            return None

        metadata = {
            "strategy_version": "xau_liquidity_type3_baseline_v1_1",
            "session": _session_label(confirmation_time),
            "liquidity_level": state["liquidity_price"],
            "liquidity_level_time": state["liquidity_time"].isoformat(),
            "sweep_time": state["sweep_time"].isoformat(),
            "sweep_price": state["sweep_price"],
            "sweep_size": abs(float(state["sweep_price"]) - float(state["liquidity_price"])),
            "type3_confirmation_time": confirmation_time.isoformat(),
            "swing_level_broken": float(state["break_level"]),
            "swing_level_time": state["break_level_time"].isoformat() if state.get("break_level_time") else None,
            "impulse_high": impulse_high,
            "impulse_low": impulse_low,
            "entry_retrace": retrace,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "target_r": target_r,
        }
        return EntrySignal(
            state["direction"], stop_loss=stop, take_profit=target,
            reason="liquidity_sweep_type3_50pct", metadata=metadata,
            order_type="limit", entry_price=entry,
            max_wait_bars=int(self.params["limit_wait_bars"]),
        )



def _strongest_pre_extreme_pivot(
    frame: pd.DataFrame,
    kind: str,
    left: int,
    right: int,
    *,
    before: datetime,
    lookback_bars: int,
    minimum_structure_bars: int,
):
    """Return the strongest confirmed opposing pivot in bounded pre-extreme structure.

    v1 used the latest tiny 1m pivot, which over-triggered on microstructure. v1.1
    deliberately chooses the highest pivot high for a long setup (or lowest pivot
    low for a short) from a fixed lookback window, while leaving at least a small
    number of bars between the pivot search and the sweep/extreme. No future bars
    are used: StrategyContext contains completed bars and every pivot still needs
    its right-hand confirmation bars.
    """
    if frame is None or len(frame) < left + right + 1:
        return None
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    before_idx = [i for i, stamp in enumerate(timestamps) if _ts(stamp) < before]
    if not before_idx:
        return None
    last_before = before_idx[-1]
    end = last_before - max(0, int(minimum_structure_bars))
    if end < left:
        return None
    start = max(left, end - max(1, int(lookback_bars)) + 1)
    stop = min(end, len(frame) - right - 1)
    if stop < start:
        return None

    values = pd.to_numeric(frame[kind], errors="coerce").tolist()
    candidates = []
    for i in range(start, stop + 1):
        value = float(values[i])
        left_values = [float(x) for x in values[i-left:i]]
        right_values = [float(x) for x in values[i+1:i+1+right]]
        valid = (kind == "low" and value < min(left_values) and value <= min(right_values)) or (
            kind == "high" and value > max(left_values) and value >= max(right_values)
        )
        if valid:
            candidates.append({"time": _ts(timestamps.iloc[i]), "price": value})
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["price"]) if kind == "high" else min(candidates, key=lambda item: item["price"])


def _latest_confirmed_pivot(frame: pd.DataFrame, kind: str, left: int, right: int, before: datetime | None = None):
    if frame is None or len(frame) < left + right + 1:
        return None
    values = pd.to_numeric(frame[kind], errors="coerce").tolist()
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    last = None
    # Because StrategyContext only supplies completed bars, requiring right bars
    # here makes every returned pivot fully confirmed without future leakage.
    for i in range(left, len(frame) - right):
        stamp = _ts(timestamps.iloc[i])
        if before is not None and stamp >= before:
            continue
        value = float(values[i])
        left_values = [float(x) for x in values[i-left:i]]
        right_values = [float(x) for x in values[i+1:i+1+right]]
        if kind == "low" and value < min(left_values) and value <= min(right_values):
            last = {"time": stamp, "price": value}
        elif kind == "high" and value > max(left_values) and value >= max(right_values):
            last = {"time": stamp, "price": value}
    return last


def _session_label(when: datetime) -> str:
    active: list[str] = []
    tokyo = when.astimezone(TOKYO).time()
    london = when.astimezone(LONDON).time()
    new_york = when.astimezone(NEW_YORK).time()
    if 9 <= tokyo.hour < 18:
        active.append("Asia")
    if 8 <= london.hour < 17:
        active.append("London")
    if 8 <= new_york.hour < 17:
        active.append("New York")
    return " / ".join(active) + (" overlap" if len(active) > 1 else "") if active else "Outside named sessions"


def _ts(value) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.to_pydatetime()
