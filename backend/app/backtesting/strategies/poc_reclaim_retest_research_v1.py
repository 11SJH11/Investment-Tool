"""
Ledger research strategy: accumulation sweep -> POC-proxy reclaim -> POC-proxy retest.

IMPORTANT DATA LIMITATION
-------------------------
Ordinary OHLCV bars do not contain exchange volume-at-price, so a true market-profile
Point of Control (POC) cannot be reconstructed from them. This v1 therefore uses an
explicit, reproducible *bar-volume POC proxy*: each completed bar contributes all of
its volume to the price bin containing its HLC3 typical price. The highest-volume bin
is the proxy POC.

This is suitable for hypothesis screening on instruments with genuine traded volume
(US equities and supported futures). It must not be described as a true exchange POC.
If Ledger later ingests tick/trade or volume-at-price data, replace only the POC source
and keep the state-machine tests so proxy-vs-true-POC results can be compared honestly.

Mechanical long sequence (short is mirrored):
1. Find the longest immediately preceding 5m accumulation window between 15 and 40
   completed bars whose total high-low width is <= 1.5 x prior 5m ATR(14).
2. Freeze that accumulation high, low and POC proxy.
3. A later completed 5m bar sweeps below the frozen accumulation low by at least
   0.05 ATR. Sweeping both sides on one bar is rejected as ambiguous.
4. Within 12 completed bars, price must close back inside the accumulation and then
   close above the frozen POC proxy.
5. After the reclaim, within 10 completed bars price must retest the POC zone and
   close back above it. A completed close back below POC after reclaim invalidates
   the setup.
6. Signal a market entry; Ledger fills on the next bar. Initial stop is the observed
   sweep extreme and target is fixed 2R from the actual fill to that stop.

The rules are intentionally simple and pre-specified for first-pass screening.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.data.instruments import instrument_spec


KEY = "poc_reclaim_retest_research_v1"


@dataclass(frozen=True)
class Accumulation:
    start_time: pd.Timestamp
    end_time: pd.Timestamp
    low: float
    high: float
    width: float
    atr: float
    poc: float
    poc_bin_low: float
    poc_bin_high: float
    bars: int


def _finite_ohlcv(frame: pd.DataFrame) -> bool:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return False
    numeric = frame[["open", "high", "low", "close", "volume"]]
    if not numeric.map(lambda x: pd.notna(x) and math.isfinite(float(x))).all().all():
        return False
    if (numeric[["open", "high", "low", "close"]] <= 0).any().any() or (numeric["volume"] < 0).any():
        return False
    if (frame["high"] < frame[["open", "low", "close"]].max(axis=1)).any():
        return False
    if (frame["low"] > frame[["open", "high", "close"]].min(axis=1)).any():
        return False
    return True


def _contiguous(frame: pd.DataFrame, minutes: int = 5) -> bool:
    if frame is None or frame.empty or "timestamp" not in frame:
        return False
    stamps = pd.to_datetime(frame["timestamp"], utc=True)
    return len(stamps) <= 1 or bool((stamps.diff().iloc[1:] == pd.Timedelta(minutes=minutes)).all())


def _atr_from_completed(frame: pd.DataFrame, length: int) -> float | None:
    """Simple causal ATR mean from completed, contiguous 5m bars only."""
    if frame is None or len(frame) < length + 1:
        return None
    sample = frame.tail(length + 1).reset_index(drop=True)
    if not _finite_ohlcv(sample) or not _contiguous(sample, 5):
        return None
    prev_close = sample["close"].shift(1)
    tr = pd.concat(
        [
            sample["high"] - sample["low"],
            (sample["high"] - prev_close).abs(),
            (sample["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    values = tr.iloc[1:]
    if len(values) != length or not values.map(math.isfinite).all():
        return None
    atr = float(values.mean())
    return atr if atr > 0 else None


def _bar_volume_poc_proxy(frame: pd.DataFrame, bins: int) -> tuple[float, float, float] | None:
    """Return (POC midpoint, bin low, bin high) using HLC3-volume histogram proxy."""
    if frame is None or frame.empty or bins < 2 or not _finite_ohlcv(frame):
        return None
    low = float(frame["low"].min())
    high = float(frame["high"].max())
    if not (high > low):
        return None
    total_volume = float(frame["volume"].sum())
    if not (total_volume > 0):
        return None

    width = (high - low) / bins
    weights = [0.0] * bins
    typicals = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    for typical, volume in zip(typicals, frame["volume"]):
        typical = float(typical)
        volume = float(volume)
        idx = int((typical - low) / width) if width > 0 else 0
        idx = min(max(idx, 0), bins - 1)
        weights[idx] += volume

    peak = max(weights)
    candidates = [i for i, value in enumerate(weights) if value == peak]
    # Deterministic tie-break: choose the tied bin closest to the accumulation midpoint.
    midpoint = (low + high) / 2.0
    idx = min(candidates, key=lambda i: abs((low + (i + 0.5) * width) - midpoint))
    bin_low = low + idx * width
    bin_high = bin_low + width
    return (bin_low + bin_high) / 2.0, bin_low, bin_high


def _find_accumulation(
    prior: pd.DataFrame,
    *,
    minimum_bars: int,
    maximum_bars: int,
    atr_length: int,
    max_range_atr: float,
    poc_bins: int,
) -> Accumulation | None:
    """Choose the longest immediately preceding window satisfying compression."""
    if prior is None or len(prior) < max(minimum_bars, atr_length + 1):
        return None
    atr = _atr_from_completed(prior, atr_length)
    # ATR is measured from the contiguous completed prefix ending immediately
    # before the candidate sweep and is therefore causal.
    if atr is None:
        return None
    for length in range(min(maximum_bars, len(prior)), minimum_bars - 1, -1):
        window = prior.tail(length).reset_index(drop=True)
        # Do not let an overnight/session gap masquerade as one accumulation.
        if not _contiguous(window, 5):
            continue
        low = float(window["low"].min())
        high = float(window["high"].max())
        width = high - low
        if not (width > 0 and width <= max_range_atr * atr):
            continue
        poc = _bar_volume_poc_proxy(window, poc_bins)
        if poc is None:
            continue
        poc_price, poc_low, poc_high = poc
        return Accumulation(
            start_time=pd.Timestamp(window.iloc[0]["timestamp"]),
            end_time=pd.Timestamp(window.iloc[-1]["timestamp"]),
            low=low,
            high=high,
            width=width,
            atr=atr,
            poc=poc_price,
            poc_bin_low=poc_low,
            poc_bin_high=poc_high,
            bars=length,
        )
    return None


@strategy_registry.register
class PocReclaimRetestResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="POC Reclaim-Retest · research v1",
        description=(
            "5m accumulation -> liquidity sweep -> reclaim of a frozen bar-volume POC proxy -> "
            "POC retest/hold -> next-bar entry. True exchange POC requires volume-at-price data."
        ),
        defaults={
            "direction": "both",
            "accumulation_min_bars": 15,
            "accumulation_max_bars": 40,
            "atr_length": 14,
            "max_range_atr": 1.5,
            "poc_bins": 24,
            "sweep_buffer_atr": 0.05,
            "max_reclaim_bars": 12,
            "max_retest_bars": 10,
            "retest_tolerance_atr": 0.10,
            "target_r": 2.0,
        },
        timeframes=("5m",),
        category="Auction / liquidity research",
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("accumulation_min_bars", "Accumulation minimum bars", "int", 15, 5, 60, 1),
            ParameterSpec("accumulation_max_bars", "Accumulation maximum bars", "int", 40, 10, 120, 1),
            ParameterSpec("atr_length", "ATR length", "int", 14, 5, 100, 1),
            ParameterSpec("max_range_atr", "Maximum accumulation width / ATR", "float", 1.5, 0.5, 10.0, 0.25),
            ParameterSpec("poc_bins", "POC proxy price bins", "int", 24, 8, 100, 1),
            ParameterSpec("sweep_buffer_atr", "Minimum sweep beyond range / ATR", "float", 0.05, 0.0, 2.0, 0.05),
            ParameterSpec("max_reclaim_bars", "Maximum bars sweep to POC reclaim", "int", 12, 1, 100, 1),
            ParameterSpec("max_retest_bars", "Maximum bars reclaim to retest", "int", 10, 1, 100, 1),
            ParameterSpec("retest_tolerance_atr", "POC retest tolerance / ATR", "float", 0.10, 0.0, 2.0, 0.05),
        ),
        research_parameters=(
            ParameterSpec("target_r", "Fixed target R", "float", 2.0, 0.5, 8.0, 0.25),
        ),
        risk_management={
            "Entry": "Next-bar market entry after completed 5m POC-proxy retest/hold",
            "Stop": "Observed sweep extreme",
            "Target": "Fixed 2R from actual fill to initial stop",
            "POC": "HLC3 bar-volume histogram proxy; not true exchange volume-at-price POC",
            "Management": "No trailing, breakeven or partial exits in v1",
        },
        source_file="backend/app/backtesting/strategies/poc_reclaim_retest_research_v1.py",
    )

    def __init__(self, **params):
        super().__init__(**params)
        p = self.params
        if p["direction"] not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")
        for key in ("accumulation_min_bars", "accumulation_max_bars", "atr_length", "poc_bins", "max_reclaim_bars", "max_retest_bars"):
            value = int(p[key])
            if value <= 0:
                raise ValueError(f"{key} must be positive")
            p[key] = value
        if p["accumulation_min_bars"] > p["accumulation_max_bars"]:
            raise ValueError("accumulation_min_bars cannot exceed accumulation_max_bars")
        for key in ("max_range_atr", "sweep_buffer_atr", "retest_tolerance_atr", "target_r"):
            value = float(p[key])
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
            p[key] = value
        if p["max_range_atr"] <= 0 or p["target_r"] <= 0:
            raise ValueError("max_range_atr and target_r must be positive")
        self.reset()

    def reset(self) -> None:
        self._state: dict | None = None

    def _invalidate(self) -> None:
        self._state = None

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "5m":
            raise ValueError("POC reclaim-retest v1 requires primary 5m bars")
        asset_type = instrument_spec(ctx.symbol).asset_type
        if asset_type not in {"equity", "future"}:
            raise ValueError("POC reclaim-retest v1 requires an equity or futures instrument with traded volume")
        if ctx.position is not None:
            return None

        needed = max(
            int(self.params["accumulation_max_bars"]) + 2,
            int(self.params["atr_length"]) + 2,
        )
        bars = ctx.bars("5m", count=needed)
        if bars is None or len(bars) < needed or not _finite_ohlcv(bars):
            return None
        bars = bars.sort_values("timestamp").reset_index(drop=True)
        current = bars.iloc[-1]
        current_time = pd.Timestamp(current["timestamp"])
        high = float(current["high"])
        low = float(current["low"])
        close = float(current["close"])

        # ----- Existing setup state -----
        if self._state is not None:
            state = self._state
            acc: Accumulation = state["accumulation"]
            side = state["direction"]
            state["bars_since_sweep"] += 1

            if side == "long":
                state["sweep_extreme"] = min(float(state["sweep_extreme"]), low)
            else:
                state["sweep_extreme"] = max(float(state["sweep_extreme"]), high)

            if state["phase"] == "swept":
                if state["bars_since_sweep"] > int(self.params["max_reclaim_bars"]):
                    self._invalidate()
                    return None

                if side == "long":
                    if close > acc.low:
                        state["reentered"] = True
                    reclaimed = state["reentered"] and close > acc.poc
                else:
                    if close < acc.high:
                        state["reentered"] = True
                    reclaimed = state["reentered"] and close < acc.poc

                if reclaimed:
                    state["phase"] = "reclaimed"
                    state["reclaim_time"] = current_time
                    state["bars_since_reclaim"] = 0
                return None

            state["bars_since_reclaim"] += 1
            if state["bars_since_reclaim"] > int(self.params["max_retest_bars"]):
                self._invalidate()
                return None

            tolerance = float(self.params["retest_tolerance_atr"]) * acc.atr
            if side == "long":
                # A completed close back below POC means the reclaim failed.
                if close < acc.poc:
                    self._invalidate()
                    return None
                touched = low <= acc.poc + tolerance and high >= acc.poc - tolerance
                held = close >= acc.poc
            else:
                if close > acc.poc:
                    self._invalidate()
                    return None
                touched = high >= acc.poc - tolerance and low <= acc.poc + tolerance
                held = close <= acc.poc

            if not (touched and held):
                return None

            stop = float(state["sweep_extreme"])
            # Signal close must still be on the correct side of the structural stop.
            if (side == "long" and not close > stop) or (side == "short" and not close < stop):
                self._invalidate()
                return None

            metadata = {
                "strategy_version": KEY,
                "direction": side,
                "signal_time": current_time.isoformat(),
                "accumulation_start": acc.start_time.isoformat(),
                "accumulation_end": acc.end_time.isoformat(),
                "accumulation_bars": acc.bars,
                "accumulation_low": acc.low,
                "accumulation_high": acc.high,
                "accumulation_width": acc.width,
                "prior_atr": acc.atr,
                "accumulation_width_atr": acc.width / acc.atr,
                "poc_proxy": acc.poc,
                "poc_proxy_bin_low": acc.poc_bin_low,
                "poc_proxy_bin_high": acc.poc_bin_high,
                "poc_method": "hlc3_bar_volume_histogram_proxy",
                "sweep_time": state["sweep_time"].isoformat(),
                "sweep_extreme": stop,
                "reclaim_time": state["reclaim_time"].isoformat(),
                "retest_time": current_time.isoformat(),
                "bars_sweep_to_reclaim": state["bars_since_sweep"] - state["bars_since_reclaim"],
                "bars_reclaim_to_retest": state["bars_since_reclaim"],
                "target_r": float(self.params["target_r"]),
            }
            self._invalidate()
            return EntrySignal(
                direction=side,
                stop_loss=stop,
                target_r=float(self.params["target_r"]),
                reason="poc_proxy_reclaim_retest",
                metadata=metadata,
            )

        # ----- Search for a new accumulation immediately before the current bar -----
        prior = bars.iloc[:-1].reset_index(drop=True)
        acc = _find_accumulation(
            prior,
            minimum_bars=int(self.params["accumulation_min_bars"]),
            maximum_bars=int(self.params["accumulation_max_bars"]),
            atr_length=int(self.params["atr_length"]),
            max_range_atr=float(self.params["max_range_atr"]),
            poc_bins=int(self.params["poc_bins"]),
        )
        if acc is None:
            return None

        buffer_distance = float(self.params["sweep_buffer_atr"]) * acc.atr
        swept_low = low < acc.low - buffer_distance
        swept_high = high > acc.high + buffer_distance
        if swept_low and swept_high:
            return None

        direction = str(self.params["direction"])
        if swept_low and direction in {"both", "long"}:
            self._state = {
                "phase": "swept",
                "direction": "long",
                "accumulation": acc,
                "sweep_time": current_time,
                "sweep_extreme": low,
                "bars_since_sweep": 0,
                "reentered": False,
                "reclaim_time": None,
                "bars_since_reclaim": 0,
            }
        elif swept_high and direction in {"both", "short"}:
            self._state = {
                "phase": "swept",
                "direction": "short",
                "accumulation": acc,
                "sweep_time": current_time,
                "sweep_extreme": high,
                "bars_since_sweep": 0,
                "reentered": False,
                "reclaim_time": None,
                "bars_since_reclaim": 0,
            }
        return None
