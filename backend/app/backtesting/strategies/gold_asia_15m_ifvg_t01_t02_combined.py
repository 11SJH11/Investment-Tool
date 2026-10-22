"""Gold Asia 15m IFVG — combined T01 + T02 research strategy.

Installation: place next to BOTH existing strategy modules in
backend/app/backtesting/strategies/, then use "Refresh strategies" in Ledger.

Frozen comparison: retains V1 first-same-Asia-session 15m IFVG, structural
stop, next-1m-open entry, 1.0R target and +0.68R breakeven management.

T01: reject the FIRST IFVG if confirmed at 23:00–23:59 America/New_York.
T02: reject the FIRST IFVG if FVG size / abs(signal-time 1m close - stop) > .20.
A setup qualifies only if BOTH filters pass. A rejected first setup consumes
that session; no replacement IFVG is considered.

The signal-close ratio is intentional: using the next-bar fill price here
would introduce lookahead. This is research-only, not broker-execution proof.
"""

from __future__ import annotations

from dataclasses import replace

from app.backtesting.strategies.gold_asia_15m_ifvg_loss_tests_v2 import (
    _ControlledGoldChild,
)
from app.backtesting.strategies.gold_asia_15m_ifvg_research_v1 import (
    GoldAsia15mIfvgResearchV1,
)
from app.backtesting.strategies.registry import strategy_registry


@strategy_registry.register
class GoldIfvgT01T02Combined(_ControlledGoldChild):
    """Both T01 and T02 entry filters, otherwise unchanged V1 execution rules."""

    SKIP_23_ET = True
    MAX_SIGNAL_FVG_STOP_RATIO = 0.20
    BE_TRIGGER_R = 0.68
    EXIT_ON_RECLAIM_15M = False
    TEST_CHANGE = (
        "Combined T01+T02: reject first IFVG confirmed 23:00-23:59 ET OR "
        "with FVG size / abs(signal-time 1m close - structural stop) > 0.20; "
        "never replace rejected first setup"
    )

    spec = replace(
        GoldAsia15mIfvgResearchV1.spec,
        key="gold_ifvg_v2_t01_t02_combined",
        name="Gold IFVG V2 · T01+T02 combined",
        category="Controlled Gold research",
        description=(
            "Frozen Gold Asia 15m IFVG V1 with BOTH T01 (exclude first IFVG "
            "confirmed 23:00-23:59 New York) and T02 (FVG/stop <=0.20 using "
            "the completed signal-time 1m close). Rejecting a first setup "
            "consumes the session. Otherwise retains 1R target and BE +0.68R."
        ),
        source_file=(
            "backend/app/backtesting/strategies/"
            "gold_asia_15m_ifvg_t01_t02_combined.py"
        ),
        risk_management={
            **GoldAsia15mIfvgResearchV1.spec.risk_management,
            "Research child": "Combined T01 AND T02 filters (both must pass)",
            "T01": "Exclude first IFVG confirmed at 23:00-23:59 America/New_York",
            "T02": "Require FVG size / signal-time 1m close-to-stop distance <= 0.20",
            "Filtered setup": "First setup consumes the session; do not take a later IFVG",
            "Breakeven": "After +0.68R, effective at next completed 1m open",
        },
    )
