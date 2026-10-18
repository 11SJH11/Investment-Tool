"""D6 + rolling 15m strict-2 market-structure-shift proxy."""
from dataclasses import replace
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, mss15_rolling_s2

KEY = "vwap_d6_mss15_research_v1"

@strategy_registry.register
class VwapD6Mss15ResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "rolling_15m_s2_mss_proxy"
    spec = replace(make_spec(
        KEY, "VWAP D6 + 15m MSS · research v1",
        "Frozen D6 VWAP baseline. Entry/reversal requires a directional 15m strict-2 BOS while rolling 15m structure is opposing or mixed.",
        "backend/app/backtesting/strategies/vwap_d6_mss15_research_v1.py",
        "Require rolling 15m strict-2 MSS proxy; exits remain frozen E2.",
    ), timeframes=("1m", "15m"))
    def _confluence_allows(self, ctx, side):
        return mss15_rolling_s2(ctx, side)
