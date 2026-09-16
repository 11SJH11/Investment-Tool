"""Frozen price/volume baseline. See docs/MOMENTUM_VCP_BASELINE_V1.md."""
from __future__ import annotations

import math

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

KEY = "momentum_vcp_breakout_baseline_v1"
DEFAULTS = {
    "minimum_history": 250, "ema_fast": 20, "ema_medium": 50, "sma_long": 200,
    "sma_slope_sessions": 20, "liquidity_sessions": 20,
    "min_dollar_volume": 20_000_000.0, "momentum_sessions": 60,
    "min_return_pct": 0.0, "high_sessions": 60, "max_distance_high_pct": 5.0,
    "base_min": 10, "base_max": 30, "max_base_depth_pct": 15.0,
    "contraction_recent_sessions": 5, "max_atr_ratio": 0.75,
    "max_volume_ratio": 1.0, "breakout_volume_sessions": 20,
    "breakout_volume_multiple": 1.0, "max_chase_pct": 2.0,
    "swing_left": 2, "swing_right": 2, "max_stop_distance_pct": 8.0,
}


@strategy_registry.register
class MomentumVcpBreakoutBaselineV1(Strategy):
    spec = StrategySpec(
        key=KEY, name="Momentum / VCP Breakout · baseline v1.0",
        description="Long daily US stocks: trend, liquid contracting base, completed breakout; next-open entry, structural stop and fixed 2R. Requires 250 prior bars in the selected period. Current symbol universe has survivorship bias.",
        defaults=DEFAULTS, timeframes=("1d",), category="Momentum",
        parameters=tuple(ParameterSpec(
            key=k, label=k.replace("_", " ").title(),
            kind="int" if isinstance(v, int) else "float", default=v,
            minimum=250 if k == "minimum_history" else 1 if isinstance(v, int) else (None if k == "min_return_pct" else 0),
        ) for k, v in DEFAULTS.items()),
        risk_management={"stop": "Most recent confirmed in-base swing low (2/2)",
                         "target": "Fixed 2R from actual fill; no management",
                         "entry": "Next daily open, above pivot and within 2%; structural risk cap 8%"},
        source_file="app/backtesting/strategies/momentum_vcp_breakout_baseline_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown momentum baseline parameter")
        super().__init__(**params)
        p = self.params
        for key, default in DEFAULTS.items():
            value = p[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be finite and numeric")
            if isinstance(default, int) and (value < 1 or int(value) != value):
                raise ValueError(f"{key} must be a positive integer")
            if key != "min_return_pct" and value < 0:
                raise ValueError(f"{key} cannot be negative")
            p[key] = int(value) if isinstance(default, int) else float(value)
        if not p["ema_fast"] < p["ema_medium"] < p["sma_long"]:
            raise ValueError("Require ema_fast < ema_medium < sma_long")
        if p["minimum_history"] < 250:
            raise ValueError("Baseline requires at least 250 prior completed bars")
        if not p["contraction_recent_sessions"] < p["base_min"] <= p["base_max"]:
            raise ValueError("Require recent window < base_min <= base_max")
        if not 0 < p["max_atr_ratio"] < 1 or not 0 < p["max_volume_ratio"] <= 1:
            raise ValueError("Contraction ratios must require actual contraction")
        if not 0 < p["max_base_depth_pct"] < 100 or not 0 < p["max_stop_distance_pct"] < 100:
            raise ValueError("Depth and stop caps must be between 0 and 100")

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1d":
            raise ValueError("Momentum baseline requires daily bars")
        bars = ctx.bars("1d")
        p = self.params
        required = max(p["minimum_history"], p["sma_long"] + p["sma_slope_sessions"] - 1,
                       p["base_max"] + 1, p["momentum_sessions"], p["high_sessions"],
                       p["liquidity_sessions"], p["breakout_volume_sessions"])
        if len(bars) <= required:
            return None
        # A bad or missing observation must not silently become a qualifying setup.
        numeric = bars[["open", "high", "low", "close", "volume"]]
        if not numeric.map(math.isfinite).all().all() or (numeric[["open", "high", "low", "close"]] <= 0).any().any() or (numeric.volume < 0).any():
            return None
        close = bars.close
        ema_fast = float(ctx.indicator("ema", length=p["ema_fast"]).iloc[-1])
        ema_medium = float(ctx.indicator("ema", length=p["ema_medium"]).iloc[-1])
        sma = ctx.indicator("sma", length=p["sma_long"])
        sma_now, sma_before = float(sma.iloc[-1]), float(sma.iloc[-1-p["sma_slope_sessions"]])
        if not close.iloc[-1] > ema_fast > ema_medium > sma_now or not sma_now > sma_before:
            return None
        prior = bars.iloc[:-1]
        liquidity = prior.tail(p["liquidity_sessions"])
        dollar_volume = float((liquidity.close * liquidity.volume).mean())
        return_pct = 100 * (float(close.iloc[-1]) / float(close.iloc[-1-p["momentum_sessions"]]) - 1)
        high60 = float(prior.tail(p["high_sessions"]).high.max())
        distance = 100 * (high60 - float(close.iloc[-1])) / high60
        prior_volume = float(prior.tail(p["breakout_volume_sessions"]).volume.mean())
        if (dollar_volume < p["min_dollar_volume"] or return_pct <= p["min_return_pct"]
                or distance > p["max_distance_high_pct"] or prior_volume <= 0
                or bars.volume.iloc[-1] <= prior_volume * p["breakout_volume_multiple"]):
            return None
        previous_close = bars.close.shift(1)
        tr = pd.concat([bars.high-bars.low, (bars.high-previous_close).abs(),
                        (bars.low-previous_close).abs()], axis=1).max(axis=1)
        tr_pct = 100 * tr / previous_close
        for length in range(p["base_max"], p["base_min"]-1, -1):
            base = prior.tail(length)
            pivot, base_low = float(base.high.max()), float(base.low.min())
            depth = 100 * (pivot-base_low) / pivot
            if depth > p["max_base_depth_pct"]:
                continue
            recent = p["contraction_recent_sessions"]
            base_atr = tr_pct.loc[base.index]
            early_atr, recent_atr = float(base_atr.iloc[:-recent].mean()), float(base_atr.iloc[-recent:].mean())
            early_volume, recent_volume = float(base.volume.iloc[:-recent].mean()), float(base.volume.iloc[-recent:].mean())
            if early_atr <= 0 or early_volume <= 0:
                continue
            atr_ratio, volume_ratio = recent_atr/early_atr, recent_volume/early_volume
            if atr_ratio > p["max_atr_ratio"] or volume_ratio >= p["max_volume_ratio"]:
                continue
            # Preselect the longest base using pre-N data only. Never switch to
            # a shorter/easier pivot after observing the breakout close.
            if close.iloc[-1] <= pivot:
                return None
            swing = confirmed_swing_low(base, p["swing_left"], p["swing_right"])
            stop = None if swing is None else float(swing.low)
            metadata = {
                "strategy_version": KEY, "ticker": ctx.symbol, "direction": "long",
                "breakout_date": str(pd.Timestamp(bars.timestamp.iloc[-1]).tz_convert("America/New_York").date()),
                "breakout_time": pd.Timestamp(bars.timestamp.iloc[-1]).isoformat(),
                "confirmed_at": ctx.decision_time.isoformat(),
                "base_start": pd.Timestamp(base.timestamp.iloc[0]).isoformat(),
                "base_end": pd.Timestamp(base.timestamp.iloc[-1]).isoformat(),
                "base_length": length, "base_depth_pct": depth, "base_high": pivot,
                "base_low": base_low, "pivot": pivot, "ema_fast": ema_fast,
                "ema_medium": ema_medium, "sma_long": sma_now, "sma_slope_comparison": sma_before,
                "return_pct": return_pct, "prior_high": high60, "distance_high_pct": distance,
                "average_dollar_volume": dollar_volume, "breakout_volume": float(bars.volume.iloc[-1]),
                "prior_average_volume": prior_volume, "breakout_volume_ratio": float(bars.volume.iloc[-1])/prior_volume,
                "early_atr_pct": early_atr, "recent_atr_pct": recent_atr,
                "contraction_ratio": atr_ratio, "volume_contraction_ratio": volume_ratio,
                "structural_stop": stop, "swing_low_time": None if swing is None else pd.Timestamp(swing.timestamp).isoformat(),
                "parameters": dict(p), "target_r": 2.0,
            }
            return EntrySignal(
                direction="long", stop_loss=stop, target_r=2.0,
                min_open_exclusive=pivot, max_open_inclusive=pivot*(1+p["max_chase_pct"]/100),
                max_stop_distance_pct=p["max_stop_distance_pct"], fill_time_filters_only=True,
                rejection_reason=("position_already_open" if ctx.position else "missing_structural_stop" if stop is None else None),
                reason="Completed daily momentum contraction breakout", metadata=metadata,
            )
        return None


def confirmed_swing_low(base, left=2, right=2):
    for i in range(len(base)-right-1, left-1, -1):
        low = base.low.iloc[i]
        if low < base.low.iloc[i-left:i].min() and low < base.low.iloc[i+1:i+right+1].min():
            return base.iloc[i]
    return None
