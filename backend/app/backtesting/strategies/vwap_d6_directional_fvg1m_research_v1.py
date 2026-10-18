"""D6 + recent directional 1m FVG >=5 bps within 30 minutes."""
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, directional_fvg1m_5bps_30m

KEY = "vwap_d6_directional_fvg1m_research_v1"

@strategy_registry.register
class VwapD6DirectionalFvg1mResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "directional_1m_fvg_ge5bps_within30m"
    spec = make_spec(
        KEY, "VWAP D6 + directional 1m FVG · research v1",
        "Frozen D6 VWAP baseline. Entry/reversal requires a same-session directional 1m FVG of at least 5 bps created within 30 minutes.",
        "backend/app/backtesting/strategies/vwap_d6_directional_fvg1m_research_v1.py",
        "Require directional 1m FVG >=5 bps within 30 minutes; exits remain frozen E2.",
    )
    def _confluence_allows(self, ctx, side):
        return directional_fvg1m_5bps_30m(ctx, side)
