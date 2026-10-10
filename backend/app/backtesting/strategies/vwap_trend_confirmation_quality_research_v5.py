"""VWAP Trend confirmation-quality research — Ledger v5.

Research purpose
----------------
v4 proved that three consecutive closes on one side of session VWAP work better
than weaker confirmation, but "three bars" only measures persistence. It does not
measure whether those bars actually make meaningful directional progress.

v5 preserves v4 execution semantics and adds ONE entry/reversal-only research
control:

    min_confirmation_displacement_bps

For an entry-confirmation sequence of N bars:

Long displacement:
    (final_confirmation_close / first_confirmation_open - 1) * 10_000

Short displacement:
    -(final_confirmation_close / first_confirmation_open - 1) * 10_000

A value of 0 disables the new filter.

The filter:
- uses only completed 1m bars available at the strategy decision time;
- applies to NEW entries and queued reversals;
- never blocks an already-confirmed exit;
- does not alter X25, E2, M3, daily EMA bias, sizing, session rules, or fills.

D0 should therefore be trade-for-trade equivalent to v4 when all other settings
match. D4/D5/D6 are intended as a small robustness test, not threshold mining.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math

from app.backtesting.strategies.base import ParameterSpec, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import (
    VwapTrendEntryExitDistanceResearchV4,
    _today_rth,
)


KEY = "vwap_trend_confirmation_quality_research_v5"

DEFAULTS = {
    "direction": "both",
    "entry_confirmation_bars": 3,
    "exit_confirmation_bars": 2,
    "max_entry_vwap_distance_bps": 25.0,
    "min_confirmation_displacement_bps": 0.0,
    "min_minutes_after_open": 1,
    "trend_timeframe": "1d",
    "trend_ema_length": 20,
    "engine_safety_stop_pct": 90.0,
}

REVIEW_CONFIG = {
    "version": 1,
    "series": [
        {
            "id": "vwap",
            "label": "Session VWAP",
            "indicator": "rth_vwap_bands",
            "timeframe": "1m",
            "params": {"line": "vwap"},
            "session_reset": True,
            "distance_bps_param": "max_entry_vwap_distance_bps",
        },
        {
            "id": "htf_ema",
            "label": "Completed RTH regime EMA",
            "indicator": "rth_trend_ema",
            "timeframe": "1m",
            "params": {
                "timeframe": {"parameter": "trend_timeframe"},
                "length": {"parameter": "trend_ema_length"},
            },
            "extended_history": True,
            "history_days": {
                "parameter": "trend_timeframe",
                "values": {"off": 0, "1h": 30, "4h": 75, "1d": 75, "1w": 250},
            },
        },
    ],
    "confirmation": {
        "series": "vwap",
        "entry_param": "entry_confirmation_bars",
        "exit_param": "exit_confirmation_bars",
        "exit_reason": "vwap_confirmed_reverse",
    },
    "record_attributes": {"confirmation_observed": "_streak_count"},
    "entry_fields": [
        "vwap",
        "confirmation_bars",
        "confirmation_count",
        "confirmation_displacement_bps",
        "min_confirmation_displacement_bps",
        "trend_timeframe",
        "trend_ema_length",
        "htf_close",
        "htf_ema",
        "htf_trend_state",
        "htf_filter_passed",
    ],
}


@strategy_registry.register
class VwapTrendConfirmationQualityResearchV5(VwapTrendEntryExitDistanceResearchV4):
    """v4 plus a causal minimum directional displacement for entry confirmation."""

    spec = StrategySpec(
        key=KEY,
        name="VWAP Trend Confirmation Quality · research v5",
        description=(
            "Frozen X25/E2 VWAP strategy with one research-only entry-quality "
            "control: minimum directional displacement across the confirmation bars."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research · refinement",
        parameters=(
            ParameterSpec(
                "direction", "Direction", "choice", "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "entry_confirmation_bars",
                "Entry confirmation · consecutive closes",
                "int", 3, 1, 10, 1,
            ),
            ParameterSpec(
                "exit_confirmation_bars",
                "Exit confirmation · opposite closes",
                "int", 2, 1, 10, 1,
            ),
            ParameterSpec(
                "max_entry_vwap_distance_bps",
                "Maximum entry distance from VWAP · bps (0=off)",
                "float", 25.0, 0.0, 500.0, 1.0,
            ),
            ParameterSpec(
                "min_confirmation_displacement_bps",
                "Minimum confirmation displacement · bps (0=off)",
                "float", 0.0, 0.0, 100.0, 1.0,
                help=(
                    "Directional move from the first confirmation bar open to "
                    "the final confirmation close. Applies to entries/reversals only."
                ),
            ),
            ParameterSpec(
                "min_minutes_after_open",
                "Earliest signal · minutes after 09:30",
                "int", 1, 1, 120, 1,
            ),
            ParameterSpec(
                "trend_timeframe",
                "Higher-timeframe trend filter",
                "choice", "1d",
                choices=("off", "1h", "4h", "1d", "1w"),
            ),
            ParameterSpec(
                "trend_ema_length",
                "Higher-timeframe EMA length",
                "int", 20, 5, 200, 5,
            ),
            ParameterSpec(
                "engine_safety_stop_pct",
                "Engine-only catastrophic stop · %",
                "float", 90.0, 20.0, 99.0, 1.0,
            ),
        ),
        risk_management={
            "Entry": "N completed closes on one side of causal session VWAP.",
            "Confirmation quality": (
                "Optional minimum directional displacement across the N completed "
                "confirmation bars; 0 disables."
            ),
            "Exit": "Independent opposite-close confirmation; frozen E2 uses 2.",
            "VWAP distance": "Entry/reversal-only maximum distance; frozen X25 uses 25 bps.",
            "HTF confluence": "New entries/reversals align with completed 1D EMA20 regime.",
            "Session": "Use run-level 09:30–11:30 entry window and force flat at 16:00.",
            "Stop": "Wide engine-only safety stop; use position-value sizing.",
        },
        source_file=(
            "backend/app/backtesting/strategies/"
            "vwap_trend_confirmation_quality_research_v5.py"
        ),
        review_config=REVIEW_CONFIG,
    )

    def __init__(self, **params):
        # v4 deliberately rejects unknown keys, so remove the new v5 key before
        # delegating. Strategy.__init__ still sees self.spec (v5), so the v5
        # default exists in self.params even during the parent constructor.
        displacement = params.pop(
            "min_confirmation_displacement_bps",
            DEFAULTS["min_confirmation_displacement_bps"],
        )
        super().__init__(**params)

        value = float(displacement)
        if not math.isfinite(value) or value < 0:
            raise ValueError("min_confirmation_displacement_bps must be finite and >= 0")
        self.params["min_confirmation_displacement_bps"] = value

        self._v5_ctx = None
        self._last_confirmation_displacement_bps = None

    def reset(self):
        super().reset()
        self._v5_ctx = None
        self._last_confirmation_displacement_bps = None

    def _confirmation_displacement_bps(self):
        """Directional displacement across the latest N completed 1m bars."""
        ctx = self._v5_ctx
        side = self._streak_side
        required = int(self.params["entry_confirmation_bars"])

        if ctx is None or side not in {"long", "short"} or required < 1:
            return None

        today = _today_rth(ctx.bars("1m", count=500))
        if len(today) < required:
            return None

        selected = today.tail(required)
        first_open = float(selected.iloc[0]["open"])
        final_close = float(selected.iloc[-1]["close"])
        if not (
            math.isfinite(first_open)
            and math.isfinite(final_close)
            and first_open > 0
        ):
            return None

        raw = (final_close / first_open - 1.0) * 10_000.0
        return float(raw if side == "long" else -raw)

    def _distance_allows(self, close, vwap_value):
        # Preserve the v4/X25 condition first.
        if not super()._distance_allows(close, vwap_value):
            return False

        minimum = float(self.params["min_confirmation_displacement_bps"])
        if minimum <= 0.0:
            self._last_confirmation_displacement_bps = (
                self._confirmation_displacement_bps()
            )
            return True

        displacement = self._confirmation_displacement_bps()
        self._last_confirmation_displacement_bps = displacement
        return displacement is not None and displacement >= minimum

    def _entry(self, ctx, side, vwap_value, trend_meta):
        # v4 builds the canonical EntrySignal. Add research provenance only;
        # no fill/risk semantics change.
        signal = super()._entry(ctx, side, vwap_value, trend_meta)

        displacement = trend_meta.get(
            "confirmation_displacement_bps",
            self._last_confirmation_displacement_bps,
        )
        metadata = {
            **dict(signal.metadata),
            "research_variant": "vwap_trend_confirmation_quality_v5",
            "confirmation_displacement_bps": displacement,
            "min_confirmation_displacement_bps": float(
                self.params["min_confirmation_displacement_bps"]
            ),
        }
        return replace(signal, metadata=metadata)

    def on_bar(self, ctx):
        # `_distance_allows` is called by v4 only for new entries / possible
        # reversals. Exits remain unconditional after E2 confirmation.
        self._v5_ctx = ctx
        self._last_confirmation_displacement_bps = None
        try:
            decision = super().on_bar(ctx)

            # If v4 has just queued a delayed reversal, preserve the exact
            # displacement that qualified it so the next-open entry metadata
            # describes the original decision rather than the following bar.
            if (
                self._pending_reverse is not None
                and self._pending_meta is not None
                and self._last_confirmation_displacement_bps is not None
            ):
                self._pending_meta = {
                    **dict(self._pending_meta),
                    "confirmation_displacement_bps": (
                        self._last_confirmation_displacement_bps
                    ),
                    "min_confirmation_displacement_bps": float(
                        self.params["min_confirmation_displacement_bps"]
                    ),
                }

            return decision
        finally:
            self._v5_ctx = None
