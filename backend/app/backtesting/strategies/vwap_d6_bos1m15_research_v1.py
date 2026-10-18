"""D6 + same-session 1m strict-2 directional BOS within 15 minutes."""
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, bos1m_s2_within_15m

KEY = "vwap_d6_bos1m15_research_v1"

@strategy_registry.register
class VwapD6Bos1m15ResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "current_1m_s2_directional_bos_within_15m"
    spec = make_spec(
        KEY, "VWAP D6 + 1m BOS≤15m · research v1",
        "Frozen D6 VWAP baseline. Entry/reversal requires a same-session directional strict-2 1m BOS within the previous 15 minutes.",
        "backend/app/backtesting/strategies/vwap_d6_bos1m15_research_v1.py",
        "Require directional 1m strict-2 BOS within 15 minutes; exits remain frozen E2.",
    )
    def _confluence_allows(self, ctx, side):
        return bos1m_s2_within_15m(ctx, side)
