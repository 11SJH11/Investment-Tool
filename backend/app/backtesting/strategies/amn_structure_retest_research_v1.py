"""Ledger research strategy: AMN structure -> BOS -> zone retest -> liquidity sweep.

SOURCE / SCOPE
--------------
This file operationalises the AMN model previously extracted from the user's video:

    HH/HL or LH/LL structure
        -> directional break of structure (BOS)
        -> associated demand/supply zone
        -> retracement/tap while structure remains valid
        -> liquidity sweep + reclaim
        -> entry confirmation

The video discussion did not leave exact numerical definitions for pivots, timeframe,
zone construction, maximum wait, or target. Those are therefore explicit research
parameters below rather than hidden assumptions.

Baseline mechanical definitions used in v1:
- single configurable signal timeframe; default 5m
- confirmed 2-left / 2-right pivots
- bullish structure = latest confirmed swing high > previous swing high AND latest
  confirmed swing low > previous swing low; bearish is the mirror
- bullish BOS = completed close above the latest confirmed swing high while bullish
  structure exists; bearish BOS = completed close below latest confirmed swing low
- demand/supply zone = the last opposite-colour candle before the BOS, using that
  candle's full high-low range
- structure must remain valid: bullish setup invalidates on a completed close below
  the swing low that supported the BOS; bearish setup mirrors this
- price must trade back into the frozen zone
- after BOS, a confirmed minor pivot provides the liquidity level; a completed bar
  must sweep it and close back through it in the trade direction
- signal is emitted only after that completed sweep/reclaim bar; Ledger fills next bar
- stop = observed sweep extreme
- target = fixed R from the actual fill; default 2R
- long/short are exact mirrors
- no FVG, VWAP, session, news, volume, EMA, or other confluence is required in v1

This is a causal screening implementation, not a claim of profitability.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.data.instruments import instrument_spec


KEY = "amn_structure_retest_research_v1"

_TIMEFRAMES = {
    0: "1m",
    1: "5m",
    2: "15m",
    3: "30m",
    4: "1h",
}

DEFAULTS = {
    "direction": "both",
    "signal_timeframe_code": 1,      # 0=1m, 1=5m, 2=15m, 3=30m, 4=1h
    "structure_pivot_left": 2,
    "structure_pivot_right": 2,
    "liquidity_pivot_left": 2,
    "liquidity_pivot_right": 2,
    "structure_lookback_bars": 120,
    "zone_search_bars": 12,
    "max_retest_bars": 30,
    "target_r": 2.0,
}


@dataclass(frozen=True)
class Pivot:
    index: int
    time: pd.Timestamp
    price: float


def _tf(params) -> str:
    return _TIMEFRAMES.get(int(params.get("signal_timeframe_code", 1)), "5m")


def _finite_ohlc(frame: pd.DataFrame) -> bool:
    required = {"timestamp", "open", "high", "low", "close"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return False
    numeric = frame[["open", "high", "low", "close"]]
    if not numeric.map(lambda x: pd.notna(x) and isfinite(float(x))).all().all():
        return False
    if (frame["high"] < frame[["open", "low", "close"]].max(axis=1)).any():
        return False
    if (frame["low"] > frame[["open", "high", "close"]].min(axis=1)).any():
        return False
    return True


def _confirmed_pivots(
    frame: pd.DataFrame,
    side: str,
    left: int,
    right: int,
    *,
    start_index: int = 0,
) -> list[Pivot]:
    """Return pivots whose right-hand confirmation bars are already completed."""
    if side not in {"high", "low"}:
        raise ValueError("pivot side must be high or low")
    values = frame[side].astype(float).tolist()
    out: list[Pivot] = []
    n = len(frame)
    first = max(left, start_index)
    last = n - right
    for i in range(first, last):
        v = values[i]
        left_values = values[i-left:i]
        right_values = values[i+1:i+1+right]
        if len(left_values) != left or len(right_values) != right:
            continue
        if side == "high":
            valid = all(v > x for x in left_values) and all(v > x for x in right_values)
        else:
            valid = all(v < x for x in left_values) and all(v < x for x in right_values)
        if valid:
            out.append(Pivot(i, pd.Timestamp(frame.iloc[i]["timestamp"]), float(v)))
    return out


def _latest_two_structure(frame: pd.DataFrame, left: int, right: int):
    highs = _confirmed_pivots(frame, "high", left, right)
    lows = _confirmed_pivots(frame, "low", left, right)
    if len(highs) < 2 or len(lows) < 2:
        return None
    h_prev, h_last = highs[-2], highs[-1]
    l_prev, l_last = lows[-2], lows[-1]
    bullish = h_last.price > h_prev.price and l_last.price > l_prev.price
    bearish = h_last.price < h_prev.price and l_last.price < l_prev.price
    return {
        "bullish": bullish,
        "bearish": bearish,
        "previous_high": h_prev,
        "latest_high": h_last,
        "previous_low": l_prev,
        "latest_low": l_last,
    }


def _last_opposite_candle(prior: pd.DataFrame, direction: str, search_bars: int):
    """Demand = last bearish candle before bullish BOS; supply = mirror."""
    window = prior.tail(search_bars)
    if window.empty:
        return None
    for idx in range(len(window) - 1, -1, -1):
        row = window.iloc[idx]
        op = float(row["open"])
        cl = float(row["close"])
        opposite = cl < op if direction == "long" else cl > op
        if opposite:
            return {
                "time": pd.Timestamp(row["timestamp"]),
                "low": float(row["low"]),
                "high": float(row["high"]),
            }
    return None


def _latest_liquidity_pivot(
    frame: pd.DataFrame,
    direction: str,
    left: int,
    right: int,
    *,
    after_time: pd.Timestamp,
):
    side = "low" if direction == "long" else "high"
    pivots = _confirmed_pivots(frame, side, left, right)
    pivots = [p for p in pivots if p.time > after_time]
    return pivots[-1] if pivots else None


@strategy_registry.register
class AmnStructureRetestResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="AMN Structure Retest · research v1",
        description=(
            "Mechanical AMN screening model: HH/HL or LH/LL structure -> directional BOS -> "
            "last opposite candle demand/supply zone -> zone retest while structure holds -> "
            "minor-liquidity sweep/reclaim -> next-bar entry."
        ),
        defaults=DEFAULTS,
        timeframes=("1m", "5m", "15m", "30m", "1h"),
        category="Structure / liquidity research",
        parameters=(
            ParameterSpec(
                "direction", "Direction", "choice", "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "signal_timeframe_code", "Signal timeframe code", "int",
                1, 0, 4, 1,
                help="0=1m, 1=5m, 2=15m, 3=30m, 4=1h.",
            ),
            ParameterSpec(
                "structure_pivot_left", "Structure pivot left bars", "int",
                2, 1, 10, 1,
            ),
            ParameterSpec(
                "structure_pivot_right", "Structure pivot right bars", "int",
                2, 1, 10, 1,
            ),
            ParameterSpec(
                "liquidity_pivot_left", "Liquidity pivot left bars", "int",
                2, 1, 10, 1,
            ),
            ParameterSpec(
                "liquidity_pivot_right", "Liquidity pivot right bars", "int",
                2, 1, 10, 1,
            ),
            ParameterSpec(
                "structure_lookback_bars", "Structure lookback bars", "int",
                120, 30, 500, 10,
            ),
            ParameterSpec(
                "zone_search_bars", "Opposite-candle zone search bars", "int",
                12, 1, 50, 1,
            ),
            ParameterSpec(
                "max_retest_bars", "Maximum BOS -> entry bars", "int",
                30, 1, 200, 1,
            ),
        ),
        research_parameters=(
            ParameterSpec(
                "target_r", "Target R", "float",
                2.0, 0.5, 6.0, 0.25,
                help="Fixed-R target from the actual fill to the sweep-extreme stop.",
            ),
        ),
        risk_management={
            "Structure": "Confirmed 2/2 HH+HL bullish or LH+LL bearish by default.",
            "BOS": "Completed close beyond latest confirmed structure swing in trend direction.",
            "Zone": "Full range of the last opposite-colour candle before BOS.",
            "Retest": "Price must trade back into the frozen zone without closing through structural invalidation.",
            "Liquidity confirmation": "Post-BOS confirmed minor pivot must be swept and reclaimed on a completed bar.",
            "Entry": "Signal after completed sweep/reclaim; common engine fills next bar.",
            "Stop": "Observed liquidity-sweep extreme.",
            "Target": "2R default from actual fill; research-selectable.",
            "Confluences": "None in v1.",
        },
        source_file="backend/app/backtesting/strategies/amn_structure_retest_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown AMN parameter")
        super().__init__(**params)

        p = self.params
        if p["direction"] not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")

        int_keys = (
            "signal_timeframe_code",
            "structure_pivot_left",
            "structure_pivot_right",
            "liquidity_pivot_left",
            "liquidity_pivot_right",
            "structure_lookback_bars",
            "zone_search_bars",
            "max_retest_bars",
        )
        for key in int_keys:
            value = p[key]
            if isinstance(value, bool) or int(value) != value:
                raise ValueError(f"{key} must be an integer")
            p[key] = int(value)

        if p["signal_timeframe_code"] not in _TIMEFRAMES:
            raise ValueError("signal_timeframe_code must be 0..4")

        p["target_r"] = float(p["target_r"])
        if not isfinite(p["target_r"]) or p["target_r"] <= 0:
            raise ValueError("target_r must be positive and finite")

        self.reset()

    def reset(self):
        self._state: dict | None = None
        self._last_bos_key = None

    def _clear(self):
        self._state = None

    def _arm_from_bos(self, bars: pd.DataFrame, current, structure, direction: str):
        prior = bars.iloc[:-1].copy()
        zone = _last_opposite_candle(
            prior,
            direction,
            int(self.params["zone_search_bars"]),
        )
        if zone is None:
            return None

        if direction == "long":
            bos_level = float(structure["latest_high"].price)
            invalidation = float(structure["latest_low"].price)
        else:
            bos_level = float(structure["latest_low"].price)
            invalidation = float(structure["latest_high"].price)

        bos_time = pd.Timestamp(current["timestamp"])
        key = (direction, bos_time.isoformat(), bos_level)
        if key == self._last_bos_key:
            return None
        self._last_bos_key = key

        self._state = {
            "direction": direction,
            "bos_time": bos_time,
            "bos_level": bos_level,
            "structure_invalidation": invalidation,
            "zone_time": zone["time"],
            "zone_low": float(zone["low"]),
            "zone_high": float(zone["high"]),
            "bars_waited": 0,
            "zone_tapped": False,
            "tap_time": None,
            "sweep_extreme": None,
        }
        return None

    def _manage_setup(self, bars: pd.DataFrame, current):
        state = self._state
        if state is None:
            return None

        state["bars_waited"] += 1
        if state["bars_waited"] > int(self.params["max_retest_bars"]):
            self._clear()
            return None

        direction = state["direction"]
        high = float(current["high"])
        low = float(current["low"])
        close = float(current["close"])
        now = pd.Timestamp(current["timestamp"])

        # Maintain the directional structure that existed at BOS.
        if direction == "long" and close < float(state["structure_invalidation"]):
            self._clear()
            return None
        if direction == "short" and close > float(state["structure_invalidation"]):
            self._clear()
            return None

        # Zone itself is also invalid if price closes through the far edge.
        if direction == "long" and close < float(state["zone_low"]):
            self._clear()
            return None
        if direction == "short" and close > float(state["zone_high"]):
            self._clear()
            return None

        touches_zone = low <= float(state["zone_high"]) and high >= float(state["zone_low"])
        if touches_zone and not state["zone_tapped"]:
            state["zone_tapped"] = True
            state["tap_time"] = now
            state["sweep_extreme"] = low if direction == "long" else high

        if not state["zone_tapped"]:
            return None

        if direction == "long":
            state["sweep_extreme"] = min(float(state["sweep_extreme"]), low)
        else:
            state["sweep_extreme"] = max(float(state["sweep_extreme"]), high)

        prior = bars.iloc[:-1].copy()
        pivot = _latest_liquidity_pivot(
            prior,
            direction,
            int(self.params["liquidity_pivot_left"]),
            int(self.params["liquidity_pivot_right"]),
            after_time=pd.Timestamp(state["bos_time"]),
        )
        if pivot is None:
            return None

        if direction == "long":
            confirmed = low < pivot.price and close > pivot.price
        else:
            confirmed = high > pivot.price and close < pivot.price

        if not confirmed:
            return None

        stop = float(state["sweep_extreme"])
        target_r = float(self.params["target_r"])
        metadata = {
            "amn_version": "v1",
            "direction": direction,
            "signal_timeframe": _tf(self.params),
            "bos_time": pd.Timestamp(state["bos_time"]).isoformat(),
            "bos_level": float(state["bos_level"]),
            "structure_invalidation": float(state["structure_invalidation"]),
            "zone_time": pd.Timestamp(state["zone_time"]).isoformat(),
            "zone_low": float(state["zone_low"]),
            "zone_high": float(state["zone_high"]),
            "zone_tap_time": pd.Timestamp(state["tap_time"]).isoformat(),
            "liquidity_pivot_time": pivot.time.isoformat(),
            "liquidity_level": float(pivot.price),
            "sweep_reclaim_time": now.isoformat(),
            "sweep_extreme": stop,
            "bars_bos_to_entry_signal": int(state["bars_waited"]),
            "target_r": target_r,
            "structure_pivot_left": int(self.params["structure_pivot_left"]),
            "structure_pivot_right": int(self.params["structure_pivot_right"]),
            "liquidity_pivot_left": int(self.params["liquidity_pivot_left"]),
            "liquidity_pivot_right": int(self.params["liquidity_pivot_right"]),
        }

        self._clear()
        return EntrySignal(
            direction=direction,
            stop_loss=stop,
            take_profit=None,
            target_r=target_r,
            reason="amn_zone_sweep_reclaim",
            metadata=metadata,
        )

    def on_bar(self, ctx):
        tf = _tf(self.params)
        if ctx.primary_timeframe != tf:
            raise ValueError(f"AMN research v1 requires primary timeframe {tf}")

        asset_type = instrument_spec(ctx.symbol).asset_type
        if asset_type not in {"equity", "future", "forex", "crypto"}:
            raise ValueError("AMN research v1 requires a supported tradable price series")

        if ctx.position is not None:
            return None

        needed = max(
            int(self.params["structure_lookback_bars"]),
            int(self.params["zone_search_bars"])
            + int(self.params["structure_pivot_left"])
            + int(self.params["structure_pivot_right"])
            + 10,
        )
        bars = ctx.bars(tf, count=needed)
        if bars is None or len(bars) < needed or not _finite_ohlc(bars):
            return None

        bars = bars.sort_values("timestamp").reset_index(drop=True)
        current = bars.iloc[-1]

        # Once a BOS setup is armed, manage only that frozen setup until entry or invalidation.
        if self._state is not None:
            return self._manage_setup(bars, current)

        left = int(self.params["structure_pivot_left"])
        right = int(self.params["structure_pivot_right"])
        structure = _latest_two_structure(bars.iloc[:-1].reset_index(drop=True), left, right)
        if structure is None:
            return None

        close = float(current["close"])
        allowed = str(self.params["direction"])

        bullish_bos = (
            bool(structure["bullish"])
            and close > float(structure["latest_high"].price)
            and allowed in {"both", "long"}
        )
        bearish_bos = (
            bool(structure["bearish"])
            and close < float(structure["latest_low"].price)
            and allowed in {"both", "short"}
        )

        if bullish_bos and bearish_bos:
            return None
        if bullish_bos:
            return self._arm_from_bos(bars, current, structure, "long")
        if bearish_bos:
            return self._arm_from_bos(bars, current, structure, "short")

        return None
