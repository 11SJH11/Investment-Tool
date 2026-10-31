"""BOS / liquidity / FVG: three causal, research-only Ledger strategies.

Place this ONE file inside backend/app/backtesting/strategies and click Refresh
strategies in Ledger. No MT5 or broker connectivity; signals go to Ledger only.

Interpretation (not a verbatim transcription of a discretionary video):
  V1: confirmed pivot BOS -> subsequent lower low/higher high -> FVG limit.
  V2: V1 structure -> sweep + rejection of a confirmed internal pivot -> NEW FVG.
  V3: V2 + pre-sweep shallow pullback; protected external swing intact.

Pivots are recognised only after right-hand bars CLOSE. The engine fills the
limit on a LATER completed primary bar, applies costs, and handles exits.
"""
from __future__ import annotations

from dataclasses import replace
from math import isfinite

import pandas as pd

from app.backtesting.context import StrategyContext
from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

SOURCE = "backend/app/backtesting/strategies/bos_liquidity_fvg_research_v1.py"

_BASE_SPEC = StrategySpec(
    key="bos_fvg_v1_structure",
    name="BOS FVG V1 · Structure + FVG",
    category="Experimental Gold research",
    description=(
        "Close-through-confirmed-swing BOS, later extension, then first suitable "
        "three-candle FVG midpoint limit. Mechanical hypothesis, not a proven edge."
    ),
    defaults={
        "direction": "both",
        "swing_left": 3, "swing_right": 3,
        "bos_buffer_atr": 0.0, "extension_atr": 0.05,
        "min_fvg_atr": 0.04, "setup_timeout_bars": 24,
        "sweep_buffer_atr": 0.0, "max_pullback_fraction": 0.50,
        "stop_buffer_atr": 0.10,
        "entry_fraction": 0.50, "limit_wait_bars": 12,
        "target_mode": "2r", "tick_size": 0.01,
    },
    timeframes=("5m", "15m"),
    parameters=(
        ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
        ParameterSpec("swing_left", "Pivot left bars", "int", 3, 1, 12, 1),
        ParameterSpec("swing_right", "Pivot right bars (confirmation delay)", "int", 3, 1, 12, 1),
        ParameterSpec("bos_buffer_atr", "BOS extra close distance (ATR)", "float", 0.0, 0.0, 1.0, 0.05),
        ParameterSpec("extension_atr", "After-BOS extension (ATR)", "float", 0.05, 0.0, 1.0, 0.05),
        ParameterSpec("min_fvg_atr", "Minimum FVG gap (ATR)", "float", 0.04, 0.0, 1.0, 0.02),
        ParameterSpec("setup_timeout_bars", "Max bars BOS to signal", "int", 24, 4, 200, 1),
        ParameterSpec("sweep_buffer_atr", "Liquidity sweep buffer (ATR)", "float", 0.0, 0.0, 1.0, 0.05),
        ParameterSpec("max_pullback_fraction", "V3 maximum retracement", "float", 0.50, 0.10, 0.90, 0.05),
        ParameterSpec("stop_buffer_atr", "Stop extra distance (ATR)", "float", 0.10, 0.0, 1.0, 0.05),
        ParameterSpec("entry_fraction", "FVG entry (0=near edge, 1=far edge)", "float", 0.50, 0.0, 1.0, 0.10),
        ParameterSpec("limit_wait_bars", "Limit expiry (bars)", "int", 12, 1, 100, 1),
        ParameterSpec("target_mode", "Take-profit", "choice", "2r", choices=("2r", "3r", "swing")),
        ParameterSpec("tick_size", "Price tick size", "float", 0.01, 0.01, 1.0, 0.01,
                      help="Match the exact instrument contract; for gold often 0.01, verify in Ledger."),
    ),
    risk_management={
        "Entry": "FVG fractional retracement; pending LIMIT, expires after N primary bars",
        "Initial stop V1": "Confirmed protected external swing +/- ATR buffer",
        "Initial stop V2/V3": "Liquidity sweep extreme +/- ATR buffer",
        "Take profit": "2R, 3R from actual fill, or earlier extension extreme (swing)",
        "Breakeven/partials": "Disabled (controlled baseline)",
        "Position sizing and execution": "Engine-owned; configure costs and risk in Backtest",
        "Signals": "Completed primary bars only; pivots need right-bar confirmation",
    },
    source_file=SOURCE,
)


def _pivot(bars: pd.DataFrame, side: str, left: int, right: int):
    """Return newest CONFIRMED pivot at index -right-1; never future bars."""
    if len(bars) < left + right + 1:
        return None
    i = len(bars) - right - 1
    x = float(bars.iloc[i][side])
    before = bars.iloc[i-left:i][side].astype(float)
    after = bars.iloc[i+1:i+1+right][side].astype(float)
    if side == "high":
        good = x > float(before.max()) and x >= float(after.max())
    else:
        good = x < float(before.min()) and x <= float(after.min())
    return (bars.iloc[i]["timestamp"], x) if good else None


def _atr(bars: pd.DataFrame, period: int = 14) -> float:
    view = bars.tail(period + 1)
    h = view["high"].to_numpy(dtype=float)
    l = view["low"].to_numpy(dtype=float)
    c = view["close"].to_numpy(dtype=float)
    if len(view) < period + 1:
        return float("nan")
    tr = [max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
          for i in range(1, len(view))]
    return sum(tr) / len(tr)


def _fvg(bars: pd.DataFrame, side: str, atr: float, minimum_atr: float):
    """Canonical OHLC 3-bar gap; only assessed after current candle closes."""
    if len(bars) < 3:
        return None
    old, now = bars.iloc[-3], bars.iloc[-1]
    if side == "short":
        lower, upper = float(now["high"]), float(old["low"])
    else:
        lower, upper = float(old["high"]), float(now["low"])
    if lower >= upper or upper - lower < atr * minimum_atr:
        return None
    return (lower, upper)


def _quantize(price: float, tick: float) -> float:
    # 8 decimal places are sufficient for supported trading tick configurations.
    return round(round(price / tick) * tick, 8)


class _BaseBosFvg(Strategy):
    VERSION = 1
    spec = _BASE_SPEC

    def __init__(self, **params):
        super().__init__(**params)
        self.reset()

    def reset(self) -> None:
        self._bar_number = -1
        self._last_bar_time = None
        self._pivots: dict[str, list[dict]] = {"high": [], "low": []}
        self._setup: dict | None = None

    def _track_pivots(self, bars: pd.DataFrame) -> None:
        left = int(self.params["swing_left"])
        right = int(self.params["swing_right"])
        for side in ("high", "low"):
            found = _pivot(bars, side, left, right)
            if found is None:
                continue
            ts, price = found
            last = self._pivots[side]
            if not last or last[-1]["ts"] != ts:
                last.append({"ts": ts, "price": price,
                             "bar": self._bar_number - right})
                if len(last) > 100:
                    del last[:-100]

    def _start_bos(self, bars: pd.DataFrame, atr: float) -> None:
        if not self._pivots["high"] or not self._pivots["low"]:
            return
        now, prev = bars.iloc[-1], bars.iloc[-2]
        low_pivot = self._pivots["low"][-1]
        high_pivot = self._pivots["high"][-1]
        buffer = float(self.params["bos_buffer_atr"]) * atr
        short = (float(prev["close"]) >= low_pivot["price"] and
                 float(now["close"]) < low_pivot["price"] - buffer and
                 float(now["high"]) < high_pivot["price"])
        long = (float(prev["close"]) <= high_pivot["price"] and
                float(now["close"]) > high_pivot["price"] + buffer and
                float(now["low"]) > low_pivot["price"])
        allowed = str(self.params["direction"])
        side = ("short" if short and allowed in ("both", "short") else
                "long" if long and allowed in ("both", "long") else None)
        if side is None:
            return
        self._setup = {
            "side": side, "born": self._bar_number,
            "broken_level": (low_pivot if side == "short" else high_pivot)["price"],
            "protected": (high_pivot if side == "short" else low_pivot)["price"],
            "bos_extreme": float(now["low"] if side == "short" else now["high"]),
            "extension": None, "extension_bar": None,
            "gap": None, "gap_bar": None,
            "sweep": None, "sweep_bar": None,
            "phase": "await_extension",
        }

    def _advance(self, bars: pd.DataFrame, atr: float) -> EntrySignal | None:
        s = self._setup
        assert s is not None
        side = s["side"]
        now = bars.iloc[-1]
        low, high, close = (float(now[k]) for k in ("low", "high", "close"))
        if self._bar_number - s["born"] > int(self.params["setup_timeout_bars"]):
            self._setup = None
            return None
        # Invalidate on a fresh breach of the external protected swing.
        if (side == "short" and high >= s["protected"]) or (side == "long" and low <= s["protected"]):
            self._setup = None
            return None

        # Retain each candidate gap until replaced by a newer eligible gap.
        gap = _fvg(bars, side, atr, float(self.params["min_fvg_atr"]))
        if gap is not None and (self.VERSION == 1 or s["sweep_bar"] is not None):
            s["gap"] = gap
            s["gap_bar"] = self._bar_number

        # A gap touched BEFORE the limit becomes active is already mitigated;
        # do not post an order for an old, visually attractive gap later.
        if s["gap"] is not None and s["gap_bar"] < self._bar_number:
            gl, gu = s["gap"]
            f = float(self.params["entry_fraction"])
            old_entry = (gl + (gu - gl) * f if side == "short"
                         else gu - (gu - gl) * f)
            if (side == "short" and high >= old_entry) or (side == "long" and low <= old_entry):
                s["gap"] = None
                s["gap_bar"] = None

        if s["extension_bar"] is None and self._bar_number > s["born"]:
            distance = float(self.params["extension_atr"]) * atr
            if (side == "short" and low < s["bos_extreme"] - distance) or (side == "long" and high > s["bos_extreme"] + distance):
                s["extension_bar"] = self._bar_number
                s["extension"] = low if side == "short" else high
                s["phase"] = "await_sweep" if self.VERSION > 1 else "await_entry"

        if s["extension_bar"] is not None:
            if side == "short":
                s["extension"] = min(float(s["extension"]), low)
            else:
                s["extension"] = max(float(s["extension"]), high)

        if self.VERSION > 1 and s["phase"] == "await_sweep":
            internal_side = "high" if side == "short" else "low"
            # A swing formed *after* the first extension, and confirmed before
            # the sweep, is a causal, objective internal liquidity level.
            pivots = [p for p in self._pivots[internal_side]
                      if s["extension_bar"] < p["bar"] < self._bar_number]
            if pivots:
                p = pivots[-1]
                price = float(p["price"])
                protected = float(s["protected"])
                ext = float(s["extension"])
                span = abs(protected - ext)
                pullback = abs(price - ext) / span if span > 0 else 1e9
                shallow = pullback <= float(self.params["max_pullback_fraction"])
                swept = ((high > price + atr * float(self.params["sweep_buffer_atr"]) and close < price)
                         if side == "short" else
                         (low < price - atr * float(self.params["sweep_buffer_atr"]) and close > price))
                if swept and (self.VERSION != 3 or shallow):
                    s["phase"] = "await_post_sweep_fvg"
                    s["sweep"] = high if side == "short" else low
                    s["sweep_bar"] = self._bar_number
                    # Disallow gaps formed BEFORE the sweep (no retrospective selection).
                    s["gap"] = None
                    s["gap_bar"] = None
                    if gap is not None:
                        s["gap"], s["gap_bar"] = gap, self._bar_number
                    s["internal_liquidity"] = price
                    s["pullback_fraction"] = pullback

        elif self.VERSION > 1 and s["phase"] == "await_post_sweep_fvg":
            if side == "short":
                s["sweep"] = max(float(s["sweep"]), high)
            else:
                s["sweep"] = min(float(s["sweep"]), low)

        ready = ((self.VERSION == 1 and s["extension_bar"] is not None) or
                 (self.VERSION > 1 and s["phase"] == "await_post_sweep_fvg"))
        if not ready or s["gap"] is None:
            return None
        lower, upper = s["gap"]
        fraction = float(self.params["entry_fraction"])
        # For either side a 50% retracement is the midpoint. 0 = near edge.
        raw_entry = (lower + (upper - lower) * fraction if side == "short"
                     else upper - (upper - lower) * fraction)
        tick = float(self.params["tick_size"])
        entry = _quantize(raw_entry, tick)
        if (side == "short" and close >= entry) or (side == "long" and close <= entry):
            return None  # wait for price to move away before posting limit
        anchor = float(s["protected"] if self.VERSION == 1 else s["sweep"])
        stop_raw = (anchor + float(self.params["stop_buffer_atr"]) * atr if side == "short"
                    else anchor - float(self.params["stop_buffer_atr"]) * atr)
        # Conservative tick rounding: stop further away from entry.
        from math import ceil, floor
        stop = (ceil(stop_raw / tick - 1e-8) * tick if side == "short"
                else floor(stop_raw / tick + 1e-8) * tick)
        stop = round(stop, 8)
        risk = stop - entry if side == "short" else entry - stop
        if not (isfinite(risk) and risk > 0):
            return None
        target_mode = str(self.params["target_mode"])
        target = None
        target_r = None
        if target_mode == "swing":
            target = _quantize(float(s["extension"]), tick)
            if (side == "short" and target >= entry) or (side == "long" and target <= entry):
                return None
        else:
            target_r = float(target_mode[:-1])
        metadata = {
            "strategy_version": f"bos_liquidity_fvg_v{self.VERSION}",
            "signal_time": str(bars.iloc[-1]["timestamp"]),
            "bos_level": s["broken_level"],
            "protected_swing": s["protected"],
            "extension_extreme": s["extension"],
            "fvg_lower": lower, "fvg_upper": upper,
            "internal_liquidity": s.get("internal_liquidity"),
            "sweep_extreme": s.get("sweep"),
            "pullback_fraction": s.get("pullback_fraction"),
            "entry_price_planned": entry,
            "stop_price_planned": stop,
            "target_mode": target_mode,
        }
        self._setup = None
        return EntrySignal(
            direction=side, stop_loss=stop, take_profit=target, target_r=target_r,
            order_type="limit", entry_price=entry,
            max_wait_bars=int(self.params["limit_wait_bars"]),
            reason=f"bos_fvg_v{self.VERSION}_{side}", metadata=metadata,
        )

    def on_bar(self, ctx: StrategyContext) -> EntrySignal | None:
        if ctx.primary_timeframe not in ("5m", "15m"):
            return None
        bars = ctx.bars(count=120)
        if len(bars) < max(17, int(self.params["swing_left"]) + int(self.params["swing_right"]) + 2):
            return None
        stamp = bars.iloc[-1]["timestamp"]
        if self._last_bar_time == stamp:
            return None
        self._last_bar_time = stamp
        self._bar_number += 1
        self._track_pivots(bars)
        atr = _atr(bars)
        if not isfinite(atr) or atr <= 0:
            return None
        if ctx.position is not None:
            self._setup = None
            return None
        if self._setup is None:
            self._start_bos(bars, atr)
            # V1 can use an FVG formed by the BOS bar itself.
            if self._setup is not None and self.VERSION == 1:
                gap = _fvg(bars, self._setup["side"], atr, float(self.params["min_fvg_atr"]))
                if gap is not None:
                    self._setup["gap"] = gap
                    self._setup["gap_bar"] = self._bar_number
            return None
        return self._advance(bars, atr)


@strategy_registry.register
class BosFvgV1(_BaseBosFvg):
    VERSION = 1
    spec = _BASE_SPEC


@strategy_registry.register
class BosFvgV2(_BaseBosFvg):
    VERSION = 2
    spec = replace(
        _BASE_SPEC, key="bos_fvg_v2_liquidity",
        name="BOS FVG V2 · Internal liquidity sweep",
        description="Confirmed BOS + extension + internal pivot sweep/rejection + fresh FVG limit.",
        risk_management={**_BASE_SPEC.risk_management,
                         "V2 qualification": "Sweep/reject confirmed internal pivot before new FVG"},
    )


@strategy_registry.register
class BosFvgV3(_BaseBosFvg):
    VERSION = 3
    spec = replace(
        _BASE_SPEC, key="bos_fvg_v3_shallow_sweep",
        name="BOS FVG V3 · Shallow pullback + sweep",
        description="V2 liquidity model, but internal pullback must be <= configurable fraction of external swing-to-extension span.",
        risk_management={**_BASE_SPEC.risk_management,
                         "V3 qualification": "V2 + <=50% shallow pullback of external swing-to-extension span"},
    )
