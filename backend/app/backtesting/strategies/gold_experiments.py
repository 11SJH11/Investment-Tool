"""Independent filter identities around the untouched frozen Gold plugin."""
from dataclasses import replace

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.xau_liquidity_type3 import XauLiquiditySweepType3Baseline

PREFIX = "xau_type3_experiment_"
VARIANTS = {
    "reference": (), "fvg": ("fvg",), "dxy": ("dxy",), "session": ("session",),
    "compression": ("compression",), "displacement": ("displacement",), "htf": ("htf",),
    "overextension": ("overextension",), "sweep_depth": ("sweep_depth",),
    "fvg_displacement": ("fvg", "displacement"), "dxy_session": ("dxy", "session"),
    "full_candidate": ("fvg", "dxy", "session", "compression", "displacement", "htf", "overextension", "sweep_depth"),
}
KEYS = {PREFIX + name + "_v1" for name in VARIANTS}
REFERENCE = PREFIX + "reference_v1"


def contiguous(bars, count, minutes=1):
    stamps = pd.to_datetime(bars.timestamp, utc=True)
    return len(bars) == count and (stamps.diff().iloc[1:] == pd.Timedelta(minutes=minutes)).all()


def ema_alignment(bars, long):
    if len(bars) < 23:
        return {"passed": False, "reason": "insufficient_hourly_history"}
    ema = bars.close.ewm(span=20, adjust=False).mean()
    close, latest, previous = float(bars.iloc[-1].close), float(ema.iloc[-1]), float(ema.iloc[-4])
    return dict(passed=(close > latest > previous if long else close < latest < previous),
                close=close, ema20=latest, ema20_three_bars_ago=previous)


def dxy_alignment(bars, decision_time, gold_long):
    if bars is None:
        return dict(passed=False, reason="dxy_data_unavailable", available=False)
    starts = pd.to_datetime(bars.timestamp, utc=True)
    available = starts + pd.Timedelta(hours=1)
    if "available_at" in bars:
        # Provider availability cannot make an incomplete hour available early.
        available = pd.concat([available, pd.to_datetime(bars.available_at, utc=True)], axis=1).max(axis=1)
    bars = bars.loc[available <= pd.Timestamp(decision_time)]
    available = available.loc[bars.index]
    if bars.empty or pd.Timestamp(decision_time)-available.iloc[-1] > pd.Timedelta(hours=2):
        return dict(passed=False, reason="dxy_stale_or_missing", available=False)
    if not contiguous(bars.tail(4), 4, 60):
        return dict(passed=False, reason="dxy_missing_hours", available=False)
    return {**ema_alignment(bars, not gold_long), "available": True,
            "last_available_at": available.iloc[-1].isoformat()}


def evaluate_filters(signal, one, hourly, decision_time, filters, dxy=None):
    """Inputs must be completed prefixes (provided by StrategyContext in runs)."""
    meta = signal.metadata
    long = signal.direction == "long"
    bar = one.iloc[-1]
    stamps = pd.to_datetime(one.timestamp, utc=True)
    sweep = pd.Timestamp(meta["sweep_time"])
    prior = one.iloc[:-1].tail(15)
    atr = None
    if contiguous(prior, 15):
        tr = pd.concat([prior.high-prior.low, (prior.high-prior.close.shift()).abs(),
                        (prior.low-prior.close.shift()).abs()], axis=1).max(axis=1)
        value = float(tr.iloc[1:].mean())
        if value > 0:
            atr = value
    checks = {}
    for key in filters:
        check = {"passed": False, "reason": "insufficient_history"}
        if key == "session":
            stamp = stamps.iloc[-1]
            hours = [stamp.tz_convert(zone).hour for zone in ("Europe/London", "America/New_York")]
            check = dict(passed=any(8 <= hour < 12 for hour in hours), london_hour=hours[0], new_york_hour=hours[1])
        elif key == "dxy":
            check = dxy_alignment(dxy, decision_time, long)
        elif key == "htf":
            check = ema_alignment(hourly, long)
        elif key == "compression":
            base = one.loc[stamps < sweep].tail(20)
            if contiguous(base, 20):
                early, recent = base.iloc[:10], base.iloc[10:]
                width = float(early.high.max()-early.low.min())
                ratio = float(recent.high.max()-recent.low.min())/width if width > 0 else None
                check = dict(passed=ratio is not None and ratio <= .65, range_ratio=ratio, threshold=.65)
        elif key == "fvg":
            impulse = one.loc[stamps >= sweep].reset_index(drop=True)
            gaps = []
            for i in range(2, len(impulse)):
                triplet = impulse.iloc[i-2:i+1]
                if not contiguous(triplet, 3):
                    continue
                first, third = triplet.iloc[0], triplet.iloc[-1]
                lower, upper = ((float(first.high), float(third.low)) if long else
                                (float(third.high), float(first.low)))
                after = impulse.iloc[i+1:]
                invalid = (after.low <= lower).any() if long else (after.high >= upper).any()
                if lower < upper and lower <= signal.entry_price <= upper and not invalid:
                    gaps.append(dict(lower=lower, upper=upper, created_at=pd.Timestamp(third.timestamp).isoformat()))
            check = dict(passed=bool(gaps), overlapping_gaps=gaps)
        elif atr is not None:
            if key == "displacement":
                body = float(bar.close-bar.open)*(1 if long else -1)
                width = float(bar.high-bar.low)
                location = float(bar.close-bar.low if long else bar.high-bar.close)/width if width > 0 else None
                check = dict(passed=body/atr >= 1 and location is not None and location >= .75,
                             body_atr=body/atr, close_location=location, prior_atr=atr)
            elif key == "sweep_depth":
                ratio = float(meta["sweep_size"])/atr
                check = dict(passed=ratio >= .25, sweep_atr=ratio, threshold=.25, prior_atr=atr)
            elif key == "overextension" and contiguous(one.tail(21), 21):
                ratio = float(bar.close-one.iloc[-21].close)*(1 if long else -1)/atr
                check = dict(passed=ratio <= 3, directional_move_atr=ratio, threshold=3, prior_atr=atr)
        if not check["passed"] and "reason" not in check:
            check["reason"] = key + "_filter"
        checks[key] = check
    return checks


class GoldExperiment(XauLiquiditySweepType3Baseline):
    filters = ()

    def __init__(self, **params):
        baseline = XauLiquiditySweepType3Baseline.spec.defaults
        if any(key not in baseline or value != baseline[key] for key, value in params.items()):
            raise ValueError("Gold experiment v1 parameters are frozen; create a separate hypothesis version")
        super().__init__(**params)

    def on_bar(self, ctx):
        if ctx.symbol not in {"XAUUSD", "XAU_USD"} or ctx.primary_timeframe != "1m":
            raise ValueError("Gold experiments require XAUUSD with primary 1m")
        signal = super().on_bar(ctx)
        if not isinstance(signal, EntrySignal):
            return signal
        checks = evaluate_filters(signal, ctx.bars("1m"), ctx.bars("1h"), ctx.decision_time, self.filters)
        failed = [f"{key}:{check['reason']}" for key, check in checks.items() if not check["passed"]]
        metadata = {**signal.metadata, "experiment_key": self.spec.key,
            "confirmed_at": ctx.decision_time.isoformat(), "filter_checks": checks,
            "filters_passed": not failed, "filter_failures": failed}
        return replace(signal, metadata=metadata, rejection_reason="; ".join(failed) or None)


for _name, _filters in VARIANTS.items():
    _spec = StrategySpec(key=PREFIX + _name + "_v1",
        name="Gold Type 3 · experimental " + _name.replace("_", " "),
        description="Frozen baseline v1.1 + " + (", ".join(_filters) or "no filters (reference)")
            + (". DXY data unavailable: no eligible trades until a verified data path exists." if "dxy" in _filters else ". Objective fixed filters; not optimized."),
        defaults=dict(XauLiquiditySweepType3Baseline.spec.defaults), timeframes=("1m", "1h"),
        category="Gold experimental", source_file="backend/app/backtesting/strategies/gold_experiments.py",
        risk_management={"Entry": "Unchanged persistent 50% limit", "Stop": "Unchanged structural extreme", "Target": "Unchanged 1.5R"})
    _class = type("Gold" + _name.title().replace("_", "") + "Experiment", (GoldExperiment,),
                  {"spec": _spec, "filters": _filters, "__module__": __name__})
    globals()[_class.__name__] = strategy_registry.register(_class)
