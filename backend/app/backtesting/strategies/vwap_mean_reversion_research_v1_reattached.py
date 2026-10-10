"""Configurable VWAP mean-reversion research strategy for Ledger.

This is a research companion to the frozen VWAP baseline.  The baseline itself
should remain unchanged so existing saved runs keep their original semantics.

Core setup:
- NY cash session, 1-minute bars
- arm after a completed close outside session VWAP +/- N standard deviations
- confirm after a completed close back inside the band
- enter on Ledger's normal next-bar fill
- structural stop at the observed excursion extreme

Research controls:
- band width
- direction
- VWAP target vs fill-relative fixed-R target
- optional break-even stop after a completed bar reaches a chosen R threshold
- optional minutes-after-open gate
- optional maximum signals per session

Break-even management is causal: the trigger is observed on a completed bar and
Ledger's ManagePositionSignal applies the stop change on the next primary bar.
"""

from __future__ import annotations

from math import ceil, floor, isfinite

from app.backtesting.models import EntrySignal, ManagePositionSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.intraday_baselines import (
    NY,
    context_metadata,
    session_bars,
)
from app.data.futures import execution_contract, execution_economics
from app.indicators.rth_vwap import session_moments


KEY = "vwap_mean_reversion_research_v1"

DEFAULTS = {
    "direction": "both",
    "band_stddev": 2.0,
    "target_mode": "vwap",          # vwap | fixed_r
    "target_r": 2.0,                # used only when target_mode == fixed_r
    "breakeven_trigger_r": 0.0,     # 0 disables
    "breakeven_offset_r": 0.0,      # 0 = entry; +0.05 = lock 0.05R
    "min_minutes_after_open": 0,     # 0 = no opening delay
    "max_signals_per_session": 0,    # 0 = unlimited
}


@strategy_registry.register
class VwapMeanReversionResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="VWAP Mean Reversion · research v1",
        description=(
            "Configurable NY-session VWAP mean reversion: completed close outside "
            "VWAP +/- Nσ, completed close back inside, next-bar entry, excursion-extreme "
            "stop, selectable VWAP or fixed-R target, optional causal break-even."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Intraday research",
        parameters=(
            ParameterSpec(
                "direction", "Direction", "choice", "both",
                choices=("both", "long", "short"),
                help="Trade both sides, long mean reversions only, or short mean reversions only.",
            ),
            ParameterSpec(
                "band_stddev", "VWAP band · standard deviations", "float",
                2.0, 0.5, 5.0, 0.25,
                help="Arm after a completed close outside VWAP +/- this many session standard deviations.",
            ),
            ParameterSpec(
                "target_mode", "Take-profit mode", "choice", "vwap",
                choices=("vwap", "fixed_r"),
                help="VWAP = frozen VWAP at confirmation. fixed_r = target based on actual fill and initial risk.",
            ),
            ParameterSpec(
                "target_r", "Fixed take-profit · R", "float",
                2.0, 0.25, 10.0, 0.25,
                help="Used only when Take-profit mode is fixed_r.",
            ),
            ParameterSpec(
                "breakeven_trigger_r", "Move stop to break-even after · R", "float",
                0.0, 0.0, 10.0, 0.25,
                help="0 disables break-even. Trigger is evaluated from the completed bar high/low.",
            ),
            ParameterSpec(
                "breakeven_offset_r", "Break-even stop offset · R", "float",
                0.0, 0.0, 2.0, 0.05,
                help="0 moves to entry. 0.05 locks approximately +0.05R after activation.",
            ),
            ParameterSpec(
                "min_minutes_after_open", "Earliest signal · minutes after 09:30 ET", "int",
                0, 0, 300, 5,
                help="0 keeps the original baseline timing. 30 excludes the first half hour.",
            ),
            ParameterSpec(
                "max_signals_per_session", "Maximum signals per session (0=unlimited)", "int",
                0, 0, 50, 1,
                help="Limits emitted VWAP entries per NY session. Zero preserves unlimited baseline behaviour.",
            ),
        ),
        risk_management={
            "Initial stop": "Observed excursion extreme while the setup is armed.",
            "Take profit": "Frozen confirmation VWAP, or fill-relative fixed R.",
            "Break-even": (
                "Optional. After a completed 1m bar reaches the configured R threshold, "
                "request a stop move to entry plus the configured R offset; it applies on the next bar."
            ),
            "Session": "NY cash session 09:30-16:00 ET.",
        },
        source_file="backend/app/backtesting/strategies/vwap_mean_reversion_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown VWAP research parameter")
        super().__init__(**params)

        p = self.params
        if p["direction"] not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")
        if p["target_mode"] not in {"vwap", "fixed_r"}:
            raise ValueError("target_mode must be vwap or fixed_r")

        for key in ("band_stddev", "target_r", "breakeven_trigger_r", "breakeven_offset_r"):
            p[key] = float(p[key])
            if not isfinite(p[key]):
                raise ValueError(f"{key} must be finite")

        if p["band_stddev"] <= 0:
            raise ValueError("band_stddev must be positive")
        if p["target_r"] <= 0:
            raise ValueError("target_r must be positive")
        if p["breakeven_trigger_r"] < 0 or p["breakeven_offset_r"] < 0:
            raise ValueError("break-even values cannot be negative")
        if p["breakeven_trigger_r"] == 0 and p["breakeven_offset_r"] != 0:
            raise ValueError("breakeven_offset_r requires breakeven_trigger_r > 0")

        for key in ("min_minutes_after_open", "max_signals_per_session"):
            value = p[key]
            if isinstance(value, bool) or int(value) != value or int(value) < 0:
                raise ValueError(f"{key} must be a non-negative integer")
            p[key] = int(value)

        self.reset()

    def reset(self):
        self.day = None
        self.armed = None
        self.signals_today = 0

    def _manage_position(self, ctx):
        trigger_r = float(self.params["breakeven_trigger_r"])
        if trigger_r <= 0:
            return None

        position = ctx.position
        if position is None or position.metadata.get("breakeven_applied"):
            return None

        risk = float(position.initial_risk_per_share)
        if not isfinite(risk) or risk <= 0:
            return None

        entry = float(position.entry_price)
        bar = ctx.current_bar
        if position.direction == "long":
            trigger_price = entry + trigger_r * risk
            reached = float(bar["high"]) >= trigger_price
            candidate = entry + float(self.params["breakeven_offset_r"]) * risk
            improves_stop = candidate > float(position.stop_loss)
        else:
            trigger_price = entry - trigger_r * risk
            reached = float(bar["low"]) <= trigger_price
            candidate = entry - float(self.params["breakeven_offset_r"]) * risk
            improves_stop = candidate < float(position.stop_loss)

        if not reached:
            return None

        metadata = {
            "breakeven_applied": True,
            "breakeven_trigger_r": trigger_r,
            "breakeven_trigger_price": trigger_price,
            "breakeven_offset_r": float(self.params["breakeven_offset_r"]),
            "breakeven_stop_price": candidate,
            "breakeven_trigger_bar_time": str(bar.get("timestamp", "")),
        }

        # If the requested stop would not improve the active stop, still persist
        # the one-shot state so the strategy does not repeatedly request it.
        return ManagePositionSignal(
            new_stop_loss=candidate if improves_stop else None,
            reason="vwap_research_breakeven",
            metadata=metadata,
        )

    def on_bar(self, ctx):
        # Position management first. ManagePositionSignal is applied by Ledger on
        # the next primary bar, so a trigger cannot retroactively stop the same bar.
        if ctx.position is not None:
            return self._manage_position(ctx)

        bars = session_bars(ctx)
        if bars.empty:
            self.armed = None
            return None

        meta, expires = context_metadata(ctx, bars)
        session_date = meta["session_date"]
        if session_date != self.day:
            self.day = session_date
            self.armed = None
            self.signals_today = 0

        if ctx.decision_time >= expires:
            self.armed = None
            return None

        now_et = ctx.decision_time.astimezone(NY)
        minutes_after_open = (now_et.hour * 60 + now_et.minute) - (9 * 60 + 30)
        if minutes_after_open < int(self.params["min_minutes_after_open"]):
            self.armed = None
            return None

        limit = int(self.params["max_signals_per_session"])
        if limit > 0 and self.signals_today >= limit:
            self.armed = None
            return None

        values = session_moments(bars).iloc[-1]
        if len(bars) < 2 or not isfinite(float(values.sd)) or float(values.sd) <= 0:
            return None

        bar = bars.iloc[-1]
        close = float(bar.close)
        sd_mult = float(self.params["band_stddev"])
        vwap = float(values.vwap)
        sd = float(values.sd)
        lower = vwap - sd_mult * sd
        upper = vwap + sd_mult * sd

        if self.armed:
            self.armed["low"] = min(float(self.armed["low"]), float(bar.low))
            self.armed["high"] = max(float(self.armed["high"]), float(bar.high))

            # Confirmation: a completed close returns strictly inside the bands.
            if lower < close < upper:
                armed, self.armed = self.armed, None
                direction = armed["direction"]

                if direction not in {str(self.params["direction"]), "long" if self.params["direction"] == "both" else "", "short" if self.params["direction"] == "both" else ""}:
                    return None

                stop = float(armed["low"] if direction == "long" else armed["high"])
                _, tick, _ = execution_economics(execution_contract(ctx.symbol, ctx.current_bar))

                take_profit = None
                target_r = None
                target_mode = str(self.params["target_mode"])

                if target_mode == "vwap":
                    take_profit = vwap
                    if tick:
                        take_profit = (
                            floor(take_profit / tick) * tick
                            if direction == "long"
                            else ceil(take_profit / tick) * tick
                        )
                else:
                    target_r = float(self.params["target_r"])

                meta.update(
                    vwap=vwap,
                    standard_deviation=sd,
                    band_stddev=sd_mult,
                    lower_band=lower,
                    upper_band=upper,
                    cumulative_volume=float(values.weight),
                    excursion_start=armed["start"],
                    excursion_low=float(armed["low"]),
                    excursion_high=float(armed["high"]),
                    direction=direction,
                    structural_stop=stop,
                    target_mode=target_mode,
                    target_r=(target_r if target_r is not None else None),
                    frozen_vwap_target=(take_profit if target_mode == "vwap" else vwap),
                    breakeven_trigger_r=float(self.params["breakeven_trigger_r"]),
                    breakeven_offset_r=float(self.params["breakeven_offset_r"]),
                    minutes_after_open=minutes_after_open,
                )

                rejection = None
                if target_mode == "vwap":
                    if direction == "long" and close >= float(take_profit):
                        rejection = "confirmation_already_at_vwap_target"
                    elif direction == "short" and close <= float(take_profit):
                        rejection = "confirmation_already_at_vwap_target"

                self.signals_today += 1
                return EntrySignal(
                    direction=direction,
                    stop_loss=stop,
                    take_profit=take_profit,
                    target_r=target_r,
                    reason="vwap_band_reentry_research",
                    metadata=meta,
                    rejection_reason=rejection,
                    expires_at=expires,
                )

        # Arm a new excursion from a completed close outside the selected band.
        direction = "long" if close < lower else "short" if close > upper else None
        allowed = str(self.params["direction"])
        if direction is not None and allowed != "both" and direction != allowed:
            return None

        if direction and (not self.armed or self.armed["direction"] != direction):
            self.armed = {
                "direction": direction,
                "low": float(bar.low),
                "high": float(bar.high),
                "start": meta["confirmation_bar_time"],
            }

        return None
