"""Frozen causal ORB/VWAP rules; see docs/ORB_VWAP_BASELINES.md."""
from datetime import datetime, time, timedelta
from dataclasses import replace
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.data.futures import execution_economics, validate_execution_symbol, execution_contract
from app.data.instruments import instrument_spec
from app.indicators.rth_vwap import session_moments
from app.backtesting.strategies.orb_participation import DEFAULTS as PARTICIPATION_DEFAULTS, FILTERS, diagnostics, rejection

NY = ZoneInfo("America/New_York")
ORB = "opening_range_breakout_baseline_v1"
ORB_RESEARCH = "opening_range_breakout_research_v1"
ORB_REVERSAL = "opening_range_failed_breakout_reversal_v1"
VWAP = "vwap_mean_reversion_baseline_v1"
KEYS = {ORB, ORB_RESEARCH, ORB_REVERSAL, VWAP}
ORB_DIAGNOSTIC_KEYS = {ORB_RESEARCH, ORB_REVERSAL}
ORB_DEFAULTS = dict(range_minutes=15, target_r=2.0, confirmation="close",
                    entry_mode="direct", volume_ratio=0.0, min_range_atr=0.0,
                    trend_ema_length=0)


def validate_market(symbol, timeframe):
    if timeframe != "1m" or instrument_spec(symbol).asset_type not in {"equity", "future"}:
        raise ValueError("ORB/VWAP require one-minute US equities or supported dated futures with traded volume")
    validate_execution_symbol(symbol)


def session_bars(ctx):
    validate_market(ctx.symbol, ctx.primary_timeframe)
    bars = ctx.bars(count=1440)
    if bars.empty:
        return bars
    execution_contract(ctx.symbol,bars.iloc[-1])
    stamps = pd.to_datetime(bars.timestamp, utc=True).dt.tz_convert(NY)
    last = stamps.iloc[-1]
    minutes = stamps.dt.hour * 60 + stamps.dt.minute
    if not 570 <= minutes.iloc[-1] < 960 or ctx.decision_time.astimezone(NY).date() != last.date():
        return bars.iloc[:0]
    bars = bars.loc[(stamps.dt.date == last.date()) & (minutes >= 570) & (minutes < 960)].reset_index(drop=True)
    anchor = pd.Timestamp(datetime.combine(last.date(), time(9, 30), NY))
    expected = pd.date_range(anchor, last, freq="min").tz_convert("UTC")
    if len(bars) != len(expected) or not (pd.to_datetime(bars.timestamp, utc=True).array == expected.array).all():
        return bars.iloc[:0]
    values = bars[["open", "high", "low", "close", "volume"]]
    if (not values.map(isfinite).all().all() or (bars.volume < 0).any()
            or (bars.high < bars[["open", "low", "close"]].max(axis=1)).any()
            or (bars.low > bars[["open", "high", "close"]].min(axis=1)).any()):
        raise ValueError("Invalid intraday OHLCV")
    return bars


def context_metadata(ctx, bars):
    day = ctx.decision_time.astimezone(NY).date()
    return ({"strategy_version": "v1.0", "session": "NY cash 09:30-16:00",
             "session_date": day.isoformat(), "confirmed_at": ctx.decision_time.isoformat(),
             "confirmation_bar_time": pd.Timestamp(bars.iloc[-1].timestamp).isoformat(),
             "signal_close": float(bars.iloc[-1].close)},
            datetime.combine(day, time(16), NY))


@strategy_registry.register
class OpeningRangeBreakout(Strategy):
    spec = StrategySpec(key=ORB, name="Opening Range Breakout · baseline v1.0",
        description="Completed 1m close beyond the 09:30 NY 15m range; next open, opposite-edge stop, 2R. Traded volume instruments only.",
        defaults=ORB_DEFAULTS, timeframes=("1m",), category="Intraday baseline",
        risk_management={"entry": "Next-bar open before 16:00 NY", "stop": "Opposite range edge", "target": "2R"})

    def __init__(self, **params):
        super().__init__(**params)
        if self.spec.key == ORB and self.params != ORB_DEFAULTS:
            raise ValueError("ORB baseline is frozen; use the research variant")
        p = self.params
        if set(p) != set(ORB_DEFAULTS):
            raise ValueError("Unknown ORB parameter")
        if str(p["range_minutes"]) not in {"5", "15", "30"}:
            raise ValueError("Opening range must be 5, 15 or 30 minutes")
        p["range_minutes"] = int(p["range_minutes"])
        if p["confirmation"] not in {"close", "wick"} or p["entry_mode"] not in {"direct", "retest"}:
            raise ValueError("Invalid ORB confirmation or entry mode")
        for key in ("target_r", "volume_ratio", "min_range_atr", "trend_ema_length"):
            p[key] = float(p[key])
            if not isfinite(p[key]) or p[key] < 0:
                raise ValueError("ORB numeric parameters must be finite and nonnegative")
        if not 0 < p["target_r"] <= 10 or p["trend_ema_length"] % 1 or p["trend_ema_length"] > 390:
            raise ValueError("Invalid ORB target or EMA length")
        self.reset()

    def reset(self):
        self.used = set()

    def on_bar(self, ctx):
        bars = session_bars(ctx)
        n = self.params["range_minutes"]
        if len(bars) <= n or ctx.position is not None:
            return None
        meta, expires = context_metadata(ctx, bars)
        if ctx.decision_time >= expires:
            return None
        base, bar = bars.iloc[:n], bars.iloc[-1]
        high, low = float(base.high.max()), float(base.low.min())
        if high <= low:
            return None
        wick = self.params["confirmation"] == "wick"
        up = float(bar.high if wick else bar.close) > high
        down = float(bar.low if wick else bar.close) < low
        if not up and not down:
            return None
        direction = "long" if up else "short"
        identity = (meta["session_date"], direction)
        if identity in self.used:
            return None
        self.used.add(identity)
        meta.update(or_high=high, or_low=low, range_minutes=n, range_width=high-low,
                    range_start=pd.Timestamp(base.iloc[0].timestamp).isoformat(),
                    range_end=(pd.Timestamp(base.iloc[-1].timestamp) + pd.Timedelta(minutes=1)).isoformat(),
                    breakout_time=meta["confirmed_at"], direction=direction)
        rejection = "ambiguous_wick_breakout" if up and down else None
        prior = bars.iloc[:-1]
        p = self.params
        if p["volume_ratio"]:
            average = float(prior.volume.tail(20).mean())
            meta["breakout_volume_ratio"] = float(bar.volume) / average if average > 0 else None
            if len(prior) < 20 or average <= 0 or float(bar.volume) < p["volume_ratio"] * average:
                rejection = rejection or "volume_filter"
        if p["min_range_atr"]:
            tr = pd.concat([prior.high-prior.low, (prior.high-prior.close.shift()).abs(),
                            (prior.low-prior.close.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.tail(14).mean())
            meta["prior_atr"] = atr
            if len(prior) < 15 or atr <= 0 or high-low < p["min_range_atr"] * atr:
                rejection = rejection or "range_atr_filter"
        if p["trend_ema_length"]:
            ema = float(bars.close.ewm(span=int(p["trend_ema_length"]), adjust=False).mean().iloc[-1])
            meta["trend_ema"] = ema
            if len(bars) < p["trend_ema_length"] or (float(bar.close) <= ema if up else float(bar.close) >= ema):
                rejection = rejection or "trend_filter"
        retest = p["entry_mode"] == "retest"
        if retest:
            expires = min(expires, ctx.decision_time + timedelta(minutes=15))
        return EntrySignal(direction=direction, stop_loss=low if up else high, target_r=p["target_r"],
            reason="opening_range_breakout", metadata=meta, rejection_reason=rejection,
            order_type="limit" if retest else "market", entry_price=(high if up else low) if retest else None,
            max_wait_bars=15 if retest else None, expires_at=expires)


class _OpeningRangeResearchRules(OpeningRangeBreakout):
    spec = StrategySpec(key=ORB_RESEARCH, name="Opening Range Breakout · experimental research",
        description="Separate experimental identity; change one variable at a time. No optimized defaults.",
        defaults=ORB_DEFAULTS, timeframes=("1m",), category="Experimental",
        parameters=(
            ParameterSpec("range_minutes", "Opening range minutes", "choice", 15, choices=("5", "15", "30")),
            ParameterSpec("confirmation", "Confirmation", "choice", "close", choices=("close", "wick")),
            ParameterSpec("entry_mode", "Entry", "choice", "direct", choices=("direct", "retest")),
            ParameterSpec("target_r", "Target R", "float", 2.0, minimum=0.1, maximum=10),
            ParameterSpec("volume_ratio", "Prior 20-bar volume multiple (0 off)", "float", 0.0, minimum=0),
            ParameterSpec("min_range_atr", "Minimum range / prior ATR14 (0 off)", "float", 0.0, minimum=0),
            ParameterSpec("trend_ema_length", "Session EMA length (0 off)", "int", 0, minimum=0, maximum=390)))


@strategy_registry.register
class OpeningRangeResearch(Strategy):
    """Wrap unchanged research signal rules; disabled filters preserve executions."""
    spec = replace(_OpeningRangeResearchRules.spec,
        defaults={**ORB_DEFAULTS, **PARTICIPATION_DEFAULTS}, timeframes=("1m", "1d"),
        parameters=_OpeningRangeResearchRules.spec.parameters + tuple(
            ParameterSpec(
                key, key.replace("_", " ").capitalize()+" (-1 off)", "float", -1.0,
                minimum=-1, maximum=maximum,
                help=("Research only. -1 disables. Upper breakout/range RVOL bounds are exclusive; "
                      "the legacy ATR-regime maximum remains inclusive for saved-run compatibility."),
                paired_max_key={
                    "min_breakout_range_atr": "max_breakout_range_atr",
                    "min_opening_range_rvol": "max_opening_range_rvol",
                }.get(key, ""),
                bound_semantics=("minimum inclusive" if key.startswith("min_") else
                                 "maximum exclusive" if key in {"max_breakout_range_atr","max_opening_range_rvol"} else
                                 "maximum inclusive" if key.startswith("max_") else ""),
            )
            for key,(_,_,maximum) in FILTERS.items()))

    def __init__(self, **params):
        super().__init__(**params)
        if set(self.params) != set(self.spec.defaults):
            raise ValueError("Unknown ORB research parameter")
        self.rules = _OpeningRangeResearchRules(**{k:self.params[k] for k in ORB_DEFAULTS})
        self.diagnostic_history = None
        self.params.update(self.rules.params)
        for key,(_,_,maximum) in FILTERS.items():
            value = float(self.params[key])
            if not isfinite(value) or (value<0 and value!=-1) or (maximum is not None and value>maximum):
                raise ValueError(f"Invalid {key}: use -1 (off) or a valid nonnegative threshold")
            self.params[key] = value
        lo,hi = self.params["min_atr_regime_percentile"],self.params["max_atr_regime_percentile"]
        if lo>=0 and hi>=0 and lo>hi:
            raise ValueError("ATR regime minimum exceeds maximum")
        for lower,upper,label in (("min_breakout_range_atr","max_breakout_range_atr","Breakout ATR"),
                                  ("min_opening_range_rvol","max_opening_range_rvol","Opening-range RVOL")):
            lo,hi=self.params[lower],self.params[upper]
            if lo>=0 and hi>=0 and lo>=hi:
                raise ValueError(f"{label} band requires minimum < exclusive maximum")

    def reset(self):
        self.rules.reset()

    def on_bar(self, ctx):
        signal = self.rules.on_bar(ctx)
        if signal is None:
            return None
        meta = {**signal.metadata, **diagnostics(ctx, self.params["range_minutes"], self.diagnostic_history)}
        return replace(signal, metadata=meta,
                       rejection_reason=signal.rejection_reason or rejection(self.params,meta))


@strategy_registry.register
class OpeningRangeFailedBreakoutReversal(Strategy):
    """First mechanical failed-ORB reversal hypothesis.

    A completed close first breaks the opening range. If a later completed bar
    closes back inside the range within the configured window, enter opposite
    the original breakout at the next bar open. The stop is the observed failed
    breakout extreme. No claim of edge is encoded here; diagnostics are retained
    so opening participation, impulse, penetration and failure speed can be tested.
    """
    spec = StrategySpec(
        key=ORB_REVERSAL,
        name="Failed ORB Reversal · research v1",
        description=("Research hypothesis: unusually active/exhausted opening breakouts may fail. "
                     "Arm on a completed OR close; reverse only after a completed close re-enters the range."),
        defaults={
            "range_minutes":15, "failure_window_minutes":30, "target_mode":"fixed_r", "target_r":1.5,
            "min_opening_range_rvol":-1.0, "max_opening_range_rvol":-1.0,
            "min_breakout_range_atr":-1.0, "max_breakout_range_atr":-1.0,
            "min_reentry_depth":-1.0,
        },
        timeframes=("1m","1d"), category="Experimental",
        parameters=(
            ParameterSpec("range_minutes","Opening range minutes","choice",15,choices=("5","15","30")),
            ParameterSpec("failure_window_minutes","Failure window minutes","int",30,minimum=1,maximum=180),
            ParameterSpec("target_mode","Target","choice","fixed_r",choices=("fixed_r","or_midpoint","opposite_edge")),
            ParameterSpec("target_r","Fixed target R","float",1.5,minimum=.1,maximum=10),
            ParameterSpec("min_opening_range_rvol","Minimum opening-range RVOL (-1 off)","float",-1.0,minimum=-1,
                          paired_max_key="max_opening_range_rvol",bound_semantics="minimum inclusive"),
            ParameterSpec("max_opening_range_rvol","Maximum opening-range RVOL (-1 off)","float",-1.0,minimum=-1,
                          bound_semantics="maximum exclusive"),
            ParameterSpec("min_breakout_range_atr","Minimum breakout range ATR (-1 off)","float",-1.0,minimum=-1,
                          paired_max_key="max_breakout_range_atr",bound_semantics="minimum inclusive"),
            ParameterSpec("max_breakout_range_atr","Maximum breakout range ATR (-1 off)","float",-1.0,minimum=-1,
                          bound_semantics="maximum exclusive"),
            ParameterSpec("min_reentry_depth","Minimum re-entry depth fraction (-1 off)","float",-1.0,minimum=-1,maximum=1,
                          help="0 is the broken OR edge; 1 is the opposite OR edge."),
        ),
        risk_management={
            "entry":"Next-bar open after completed close back inside OR",
            "stop":"Observed failed-breakout extreme",
            "target":"Research choice: fixed R, OR midpoint, or opposite OR edge",
        },
    )

    def __init__(self, **params):
        super().__init__(**params)
        if set(self.params) != set(self.spec.defaults):
            raise ValueError("Unknown failed-ORB reversal parameter")
        p=self.params
        p["range_minutes"]=int(p["range_minutes"])
        p["failure_window_minutes"]=int(p["failure_window_minutes"])
        p["target_r"]=float(p["target_r"])
        if p["range_minutes"] not in {5,15,30} or not 1<=p["failure_window_minutes"]<=180:
            raise ValueError("Invalid failed-ORB range/failure window")
        if p["target_mode"] not in {"fixed_r","or_midpoint","opposite_edge"} or not 0<p["target_r"]<=10:
            raise ValueError("Invalid failed-ORB target")
        for key in ("min_opening_range_rvol","max_opening_range_rvol","min_breakout_range_atr","max_breakout_range_atr","min_reentry_depth"):
            p[key]=float(p[key])
            if not isfinite(p[key]) or (p[key]<0 and p[key]!=-1):
                raise ValueError(f"Invalid {key}: use -1 (off) or a nonnegative value")
        if p["min_reentry_depth"]>1:
            raise ValueError("Re-entry depth cannot exceed 1")
        for lower,upper in (("min_opening_range_rvol","max_opening_range_rvol"),("min_breakout_range_atr","max_breakout_range_atr")):
            if p[lower]>=0 and p[upper]>=0 and p[lower]>=p[upper]:
                raise ValueError("Failed-ORB research band requires minimum < exclusive maximum")
        self.diagnostic_history=None
        self.reset()

    def reset(self):
        self.day=None
        self.armed=None
        self.used=set()
        self.seen_breakout=set()

    @staticmethod
    def _passes(value, lower, upper):
        if lower>=0 and (value is None or not isfinite(value) or value<lower):
            return False
        if upper>=0 and (value is None or not isfinite(value) or value>=upper):
            return False
        return True

    def on_bar(self, ctx):
        bars=session_bars(ctx)
        n=self.params["range_minutes"]
        if len(bars)<=n:
            return None
        meta,expires=context_metadata(ctx,bars)
        day=meta["session_date"]
        if day!=self.day:
            self.day=day;self.armed=None
        if ctx.position is not None or day in self.used or ctx.decision_time>=expires:
            return None
        base,bar=bars.iloc[:n],bars.iloc[-1]
        high,low=float(base.high.max()),float(base.low.min())
        if high<=low:
            return None
        close=float(bar.close)
        # Arm only on a completed close outside the range. The breakout itself is
        # not traded; its point-in-time diagnostics become context for a later failure.
        if self.armed is None:
            if day in self.seen_breakout:
                return None
            original="long" if close>high else "short" if close<low else None
            if original is None:
                return None
            self.seen_breakout.add(day)
            diag=diagnostics(ctx,n,self.diagnostic_history)
            self.armed={
                "original_direction":original, "breakout_time":ctx.decision_time,
                "breakout_bar_time":pd.Timestamp(bar.timestamp).isoformat(),
                "extreme":float(bar.high if original=="long" else bar.low),
                "or_high":high,"or_low":low,"range_width":high-low,"diagnostics":diag,
            }
            return None
        armed=self.armed
        elapsed=(ctx.decision_time-armed["breakout_time"]).total_seconds()/60
        if elapsed>self.params["failure_window_minutes"]:
            self.armed=None
            return None
        if armed["original_direction"]=="long":
            armed["extreme"]=max(float(armed["extreme"]),float(bar.high))
        else:
            armed["extreme"]=min(float(armed["extreme"]),float(bar.low))
        inside=low < close < high
        if not inside:
            return None
        reversal="short" if armed["original_direction"]=="long" else "long"
        depth=((high-close)/(high-low) if reversal=="short" else (close-low)/(high-low))
        diag=dict(armed["diagnostics"])
        extension=(float(armed["extreme"])-high if reversal=="short" else low-float(armed["extreme"]))
        prior_atr=diag.get("prior_1m_atr14")
        penetration_atr=(extension/prior_atr if prior_atr and prior_atr>0 else None)
        meta.update(diag)
        meta.update({
            "hypothesis":"high opening participation / extended OR breakout may fail and rotate back through the range",
            "failed_orb_version":"v1", "original_breakout_direction":armed["original_direction"],
            "breakout_time":armed["breakout_time"].isoformat(), "breakout_bar_time":armed["breakout_bar_time"],
            "failure_time":ctx.decision_time.isoformat(), "failure_speed_minutes":elapsed,
            "or_high":high,"or_low":low,"range_width":high-low,"failed_breakout_extreme":float(armed["extreme"]),
            "breakout_penetration":extension,"breakout_penetration_atr":penetration_atr,
            "reentry_close":close,"reentry_depth_fraction":depth,"direction":reversal,
        })
        p=self.params
        rejection_reason=None
        if not self._passes(diag.get("opening_range_rvol"),p["min_opening_range_rvol"],p["max_opening_range_rvol"]):
            rejection_reason="opening_range_rvol_filter"
        elif not self._passes(diag.get("breakout_range_atr"),p["min_breakout_range_atr"],p["max_breakout_range_atr"]):
            rejection_reason="breakout_range_atr_filter"
        elif p["min_reentry_depth"]>=0 and depth<p["min_reentry_depth"]:
            rejection_reason="reentry_depth_filter"
        stop=float(armed["extreme"])
        _,tick,_=execution_economics(execution_contract(ctx.symbol,ctx.current_bar))
        if tick:
            stop=(ceil(stop/tick) if reversal=="short" else floor(stop/tick))*tick
        take_profit=None;target_r=None
        if p["target_mode"]=="fixed_r":
            target_r=p["target_r"]
        else:
            target=(high+low)/2 if p["target_mode"]=="or_midpoint" else (low if reversal=="short" else high)
            take_profit=(ceil(target/tick) if reversal=="long" else floor(target/tick))*tick if tick else target
        self.used.add(day);self.armed=None
        return EntrySignal(direction=reversal,stop_loss=stop,take_profit=take_profit,target_r=target_r,
                           reason="failed_orb_reversal",metadata=meta,rejection_reason=rejection_reason,expires_at=expires)


@strategy_registry.register
class VwapMeanReversion(Strategy):
    spec = StrategySpec(key=VWAP, name="VWAP Mean Reversion · baseline v1.0",
        description="NY 09:30 volume-weighted HLC3 population bands: close outside 2σ then back inside; next open to frozen VWAP.",
        timeframes=("1m",), category="Intraday baseline",
        risk_management={"stop": "Observed excursion extreme", "target": "VWAP frozen at confirmation"})

    def __init__(self, **params):
        if params:
            raise ValueError("VWAP baseline is frozen and accepts no parameters")
        super().__init__()
        self.reset()

    def reset(self):
        self.day = None
        self.armed = None

    def on_bar(self, ctx):
        bars = session_bars(ctx)
        if bars.empty:
            self.armed = None
            return None
        meta, expires = context_metadata(ctx, bars)
        if meta["session_date"] != self.day:
            self.day, self.armed = meta["session_date"], None
        if ctx.position is not None or ctx.decision_time >= expires:
            self.armed = None
            return None
        values = session_moments(bars).iloc[-1]
        if len(bars) < 2 or not isfinite(values.sd) or values.sd <= 0:
            return None
        bar = bars.iloc[-1]
        close = float(bar.close)
        lower, upper = float(values.vwap-2*values.sd), float(values.vwap+2*values.sd)
        if self.armed:
            self.armed["low"] = min(self.armed["low"], float(bar.low))
            self.armed["high"] = max(self.armed["high"], float(bar.high))
            if lower < close < upper:
                armed, self.armed = self.armed, None
                direction = armed["direction"]
                stop = armed["low"] if direction == "long" else armed["high"]
                target = float(values.vwap)
                _, tick, _ = execution_economics(execution_contract(ctx.symbol,ctx.current_bar))
                if tick:
                    target = (floor(target/tick) if direction == "long" else ceil(target/tick))*tick
                meta.update(vwap=float(values.vwap), standard_deviation=float(values.sd),
                    lower_band=lower, upper_band=upper, cumulative_volume=float(values.weight),
                    excursion_start=armed["start"], excursion_low=armed["low"], excursion_high=armed["high"],
                    direction=direction, structural_stop=stop, confirmation_target=target)
                rejection = "confirmation_already_at_vwap_target" if (close >= target if direction == "long" else close <= target) else None
                return EntrySignal(direction, stop, target, reason="vwap_band_reentry", metadata=meta,
                                   rejection_reason=rejection, expires_at=expires)
        direction = "long" if close < lower else "short" if close > upper else None
        if direction and (not self.armed or self.armed["direction"] != direction):
            self.armed = {"direction": direction, "low": float(bar.low), "high": float(bar.high),
                          "start": meta["confirmation_bar_time"]}
        return None
