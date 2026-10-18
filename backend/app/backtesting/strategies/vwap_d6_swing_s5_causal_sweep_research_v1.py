"""D6 + causality-corrected strict-5 adverse swing sweep/reclaim within 5m.

IMPORTANT: the first discovery script could attribute a sweep that occurred before
its swing pivot was confirmed.  This child fixes that by requiring pivot confirmation
before the sweep.  It is DEVELOPMENT ONLY until the corrected diagnostic is rerun.
"""
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, causal_swing_s5_samebar_within5

KEY = "vwap_d6_swing_s5_causal_sweep_research_v1"

@strategy_registry.register
class VwapD6SwingS5CausalSweepResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "causal_strict5_adverse_samebar_sweep_within5m"
    spec = make_spec(
        KEY, "VWAP D6 + causal S5 sweep≤5m · research v1",
        "Frozen D6 VWAP baseline. Development-only corrected interpretation: require a same-bar adverse strict-5 swing sweep/reclaim within five minutes, with the pivot confirmed before the sweep.",
        "backend/app/backtesting/strategies/vwap_d6_swing_s5_causal_sweep_research_v1.py",
        "DEVELOPMENT ONLY: causality-corrected strict-5 adverse sweep/reclaim within 5m; exits remain frozen E2.",
    )
    def _confluence_allows(self, ctx, side):
        return causal_swing_s5_samebar_within5(ctx, side)
