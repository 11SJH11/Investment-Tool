"""D6 + reject only the strongest 20m accumulation/chop proxy state."""
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, extreme_chop_score

KEY = "vwap_d6_no_extreme_chop_research_v1"

@strategy_registry.register
class VwapD6NoExtremeChopResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "reject_accumulation_proxy_score_4"
    spec = make_spec(
        KEY, "VWAP D6 + reject extreme chop · research v1",
        "Frozen D6 VWAP baseline. Reject only when all four pre-entry chop/compression components are present; before 40 RTH minutes the filter is unavailable and passes through.",
        "backend/app/backtesting/strategies/vwap_d6_no_extreme_chop_research_v1.py",
        "Reject heuristic 20m accumulation/chop score >=4; exits remain frozen E2.",
    )
    def _confluence_allows(self, ctx, side):
        score, detail = extreme_chop_score(ctx)
        # Discovery compared the extreme available subgroup to the rest. Missing
        # early-session context is therefore not treated as evidence of chop.
        return (score is None or score < 4), detail
