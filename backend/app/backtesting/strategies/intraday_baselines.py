"""Frozen causal ORB/VWAP rules; see docs/ORB_VWAP_BASELINES.md."""
from datetime import datetime, time, timedelta
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.data.futures import execution_economics, validate_execution_symbol, execution_contract
from app.data.instruments import instrument_spec
from app.indicators.rth_vwap import session_moments

NY = ZoneInfo("America/New_York")
ORB = "opening_range_breakout_baseline_v1"
ORB_RESEARCH = "opening_range_breakout_research_v1"
VWAP = "vwap_mean_reversion_baseline_v1"
KEYS = {ORB, ORB_RESEARCH, VWAP}
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


@strategy_registry.register
class OpeningRangeResearch(OpeningRangeBreakout):
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
