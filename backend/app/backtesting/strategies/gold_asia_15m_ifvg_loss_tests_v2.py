"""Controlled Gold Asia 15m IFVG V1 *research* children.

INSTALL: Put this file ALONGSIDE the existing
  gold_asia_15m_ifvg_research_v1.py
in backend/app/backtesting/strategies/, then press Refresh strategies.

The registered variants preserve V1's first-same-session IFVG selection,
15m confirmation, next-1m-open entry, initial structural stop, and 1R target.
One explicitly stated rule is changed per variant. Do not alter the baseline.

Important:
* No executable-price or broker-lot realism is claimed by these strategies.
* Filtered first setups consume their session. A second setup is NOT substituted.
* The ratio filter uses signal-time 1m CLOSE rather than unknown next-bar fill.
* Early exit uses only a completed 15m candle; execution is next 1m open.
* Models, times, and execution semantics are inherited from the existing engine.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.gold_asia_15m_ifvg_research_v1 import (
    GoldAsia15mIfvgResearchV1,
    NY,
    _available_at,
    _ts,
)

SOURCE_FILE = (
    "backend/app/backtesting/strategies/"
    "gold_asia_15m_ifvg_loss_tests_v2.py"
)


class _ControlledGoldChild(GoldAsia15mIfvgResearchV1):
    """Shared V1 entry rules; only filters / management below can differ."""

    TEST_CHANGE = "none"
    BE_TRIGGER_R = 0.68  # None -> no BE management
    SKIP_23_ET = False
    MAX_SIGNAL_FVG_STOP_RATIO = None
    EXIT_ON_RECLAIM_15M = False

    def on_bar(self, ctx):
        # V1 uses self._manage_breakeven() through dynamic dispatch when open.
        signal = super().on_bar(ctx)
        if not isinstance(signal, EntrySignal):
            return signal

        meta = dict(signal.metadata)
        if self.SKIP_23_ET:
            when = _ts(meta["ifvg_confirmation_time"]).astimezone(NY)
            if when.hour == 23:
                # V1 consumed first IFVG before returning signal.
                return None

        if self.MAX_SIGNAL_FVG_STOP_RATIO is not None:
            # Causal proxy: the entry OPEN has not happened yet. Never use it.
            signal_close = float(ctx.current_bar["close"])
            risk_distance = abs(signal_close - float(signal.stop_loss))
            if risk_distance <= 0:
                return None
            ratio = float(meta["fvg_size"]) / risk_distance
            if ratio > self.MAX_SIGNAL_FVG_STOP_RATIO:
                return None
            meta["ifvg_fvg_to_stop_ratio_at_signal"] = ratio

        # Make generated trade evidence identify the actual child, not V1.
        meta.update({
            "strategy_version": self.spec.key,
            "baseline_strategy_key": "gold_asia_15m_ifvg_research_v1",
            "controlled_test_change": self.TEST_CHANGE,
            "source_rule": "Frozen V1 entry/stop/1R target; " + self.TEST_CHANGE,
            "breakeven_trigger_r": self.BE_TRIGGER_R,
            "breakeven_semantics": (
                "disabled" if self.BE_TRIGGER_R is None
                else "completed_1m_touch_then_next_1m_open_management"
            ),
        })
        return replace(signal, metadata=meta)

    def _manage_breakeven(self, ctx):
        position = ctx.position
        if position is None or (position.metadata or {}).get("strategy_version") != self.spec.key:
            return None

        if self.EXIT_ON_RECLAIM_15M:
            bars15 = ctx.bars("15m")
            if not bars15.empty:
                latest = bars15.iloc[-1]
                confirmation = _available_at(latest, "15m")
                # Strictly later than fill: don't use the original signal candle.
                if confirmation > _ts(position.entry_time) and confirmation <= ctx.decision_time:
                    close = float(latest["close"])
                    lower = float(position.metadata["fvg_lower"])
                    upper = float(position.metadata["fvg_upper"])
                    # Long inverted BEARISH gap by closing above upper boundary.
                    # Short inverted BULLISH gap by closing below lower boundary.
                    reclaimed = (
                        close <= upper if position.direction == "long"
                        else close >= lower
                    )
                    if reclaimed:
                        return ExitSignal(reason="ifvg_15m_reclaim_invalidation")

        trigger_r = self.BE_TRIGGER_R
        if trigger_r is None or (position.metadata or {}).get("ifvg_breakeven_armed"):
            return None
        entry = float(position.entry_price)
        risk = float(position.initial_risk_per_share)
        if risk <= 0:
            return None
        if position.direction == "long" and float(position.stop_loss) >= entry:
            return None
        if position.direction == "short" and float(position.stop_loss) <= entry:
            return None
        bar = ctx.current_bar
        trigger = entry + trigger_r * risk if position.direction == "long" else entry - trigger_r * risk
        reached = (
            float(bar["high"]) >= trigger if position.direction == "long"
            else float(bar["low"]) <= trigger
        )
        if not reached:
            return None
        return ManagePositionSignal(
            new_stop_loss=entry,
            reason="ifvg_move_stop_to_breakeven",
            metadata={
                "ifvg_breakeven_armed": True,
                "ifvg_breakeven_trigger_r": trigger_r,
                "ifvg_breakeven_trigger_price": trigger,
                "ifvg_breakeven_observed_at": ctx.decision_time.isoformat(),
                "ifvg_breakeven_application": "next_primary_bar_open",
            },
        )


def _spec(key: str, name: str, change: str, *, be: str = "after +0.68R"):
    baseline = GoldAsia15mIfvgResearchV1.spec
    return replace(
        baseline,
        key=key,
        name=name,
        category="Controlled Gold research",
        description="Frozen Gold IFVG V1 with ONE research change: " + change,
        source_file=SOURCE_FILE,
        risk_management={**baseline.risk_management,
            "Research child": change,
            "Breakeven": be,
        },
    )


@strategy_registry.register
class GoldIfvgSkip23ETV2(_ControlledGoldChild):
    SKIP_23_ET = True
    TEST_CHANGE = "Skip first IFVG confirmed 23:00-23:59 ET; do not replace it"
    spec = _spec(
        "gold_ifvg_v2_skip_23et", "Gold IFVG V2 · exclude 23:00 ET",
        TEST_CHANGE,
    )


@strategy_registry.register
class GoldIfvgRatio020V2(_ControlledGoldChild):
    MAX_SIGNAL_FVG_STOP_RATIO = 0.20
    TEST_CHANGE = "Skip first IFVG when FVG size / signal-close-to-stop distance > 0.20"
    spec = _spec(
        "gold_ifvg_v2_fvg_ratio_020", "Gold IFVG V2 · FVG/stop <= 0.20",
        TEST_CHANGE,
    )


@strategy_registry.register
class GoldIfvgBE050V2(_ControlledGoldChild):
    BE_TRIGGER_R = 0.50
    TEST_CHANGE = "Move stop to BE after a completed 1m bar reaches +0.50R"
    spec = _spec(
        "gold_ifvg_v2_be_050", "Gold IFVG V2 · BE at +0.50R",
        TEST_CHANGE, be="After +0.50R, effective at next 1m open",
    )


@strategy_registry.register
class GoldIfvgBE080V2(_ControlledGoldChild):
    BE_TRIGGER_R = 0.80
    TEST_CHANGE = "Move stop to BE after a completed 1m bar reaches +0.80R"
    spec = _spec(
        "gold_ifvg_v2_be_080", "Gold IFVG V2 · BE at +0.80R",
        TEST_CHANGE, be="After +0.80R, effective at next 1m open",
    )


@strategy_registry.register
class GoldIfvgNoBEV2(_ControlledGoldChild):
    BE_TRIGGER_R = None
    TEST_CHANGE = "Disable breakeven; retain original structural stop and 1R target"
    spec = _spec(
        "gold_ifvg_v2_no_be", "Gold IFVG V2 · no breakeven",
        TEST_CHANGE, be="Disabled",
    )


@strategy_registry.register
class GoldIfvgReclaimExitV2(_ControlledGoldChild):
    EXIT_ON_RECLAIM_15M = True
    TEST_CHANGE = "Exit next 1m open after completed 15m close reclaims inversion boundary"
    spec = _spec(
        "gold_ifvg_v2_reclaim_exit", "Gold IFVG V2 · 15m early invalidation",
        TEST_CHANGE,
    )
