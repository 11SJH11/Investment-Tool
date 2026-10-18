"""D6 + reject unresolved latest opposing 15m FVG over rolling sessions."""
from dataclasses import replace
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, no_unfilled_opposing_fvg15

KEY = "vwap_d6_no_opposing_fvg15_research_v1"

@strategy_registry.register
class VwapD6NoOpposingFvg15ResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "no_unfilled_latest_opposing_15m_fvg_rolling5"
    spec = replace(make_spec(
        KEY, "VWAP D6 + no unresolved opposing 15m FVG · research v1",
        "Frozen D6 VWAP baseline. Reject entry/reversal when the latest opposing 15m same-session FVG in the rolling five-session context remains unfilled.",
        "backend/app/backtesting/strategies/vwap_d6_no_opposing_fvg15_research_v1.py",
        "Reject unresolved latest opposing 15m FVG; exits remain frozen E2.",
    ), timeframes=("1m", "15m"))
    def _confluence_allows(self, ctx, side):
        return no_unfilled_opposing_fvg15(ctx, side)
