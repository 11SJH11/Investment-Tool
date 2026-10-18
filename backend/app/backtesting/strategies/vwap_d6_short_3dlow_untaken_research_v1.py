"""D6 + short-only rejection after prior three-session low has already been taken."""
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, short_sellside_untaken

KEY = "vwap_d6_short_3dlow_untaken_research_v1"

@strategy_registry.register
class VwapD6Short3dLowUntakenResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "short_only_prior_3d_low_not_already_taken"
    spec = make_spec(
        KEY, "VWAP D6 + short 3-day low untaken · research v1",
        "Frozen D6 VWAP baseline. Longs are unchanged; shorts are rejected once the current session has traded below the lowest low of the prior three RTH sessions before the signal.",
        "backend/app/backtesting/strategies/vwap_d6_short_3dlow_untaken_research_v1.py",
        "Short-only: require prior-three-session low not already taken; longs pass through; exits remain frozen E2.",
    )
    def _confluence_allows(self, ctx, side):
        return short_sellside_untaken(ctx, side, 3)
