"""Direction-specific VWAP D6 confluence hybrid — research v1.

Frozen development hypothesis derived from inspected 2020-01-01 -> 2026-10-02
results.  Do not retune this file on that same development sample.

Eligibility:
- LONG: require the simple B rule: 15m MSS AND no unresolved opposing 15m FVG.
- SHORT: require the C rule: preregistered confluence score >= 4/5.

The D (5/5) condition is automatically included: every 5/5 signal necessarily
passes the long B rule (it contains MSS + no-opposing-FVG) and the short C rule
(5 >= 4).  There is therefore no separate D override needed unless engine-level
trade-slot priority is intentionally changed, which this research child does NOT do.

All parent D6/X25/E2/EMA20/session/execution semantics remain unchanged.
"""
from __future__ import annotations

from dataclasses import replace

from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import (
    FrozenD6ConfluenceBase,
    directional_fvg1m_5bps_30m,
    make_spec,
    mss15_rolling_s2,
    no_unfilled_opposing_fvg15,
    short_sellside_untaken,
)
from app.backtesting.strategies.vwap_d6_combined_confluences_research_v1 import (
    _middle_volatility_25_75,
)

KEY = "vwap_d6_direction_hybrid_research_v1"
SOURCE = "backend/app/backtesting/strategies/vwap_d6_direction_hybrid_research_v1.py"


@strategy_registry.register
class VwapD6DirectionHybridResearchV1(FrozenD6ConfluenceBase):
    """B for longs, C for shorts; 5/5 signals are naturally included."""

    CONFLUENCE_ID = "direction_hybrid_b_longs_c_shorts_v1"
    spec = replace(
        make_spec(
            KEY,
            "VWAP D6 + B longs / C shorts · research v1",
            (
                "Frozen direction-specific combination. Long entries/reversals require "
                "15m MSS AND no unresolved opposing 15m FVG. Short entries/reversals "
                "require >=4/5 of the preregistered score components. All 5/5 signals "
                "are automatically eligible under these rules."
            ),
            SOURCE,
            "Long: B rule. Short: C >=4/5 rule. Exits remain frozen E2.",
        ),
        timeframes=("1m", "15m"),
    )

    def reset(self):
        super().reset()
        self._tod_cache_date = None
        self._tod_prior: dict[int, list[float]] = {}

    def _score_components(self, ctx, side: str):
        mss_ok, mss_meta = mss15_rolling_s2(ctx, side)
        no_opp_ok, no_opp_meta = no_unfilled_opposing_fvg15(ctx, side)
        dir_fvg_ok, dir_fvg_meta = directional_fvg1m_5bps_30m(ctx, side)
        midvol_ok, midvol_meta = _middle_volatility_25_75(self, ctx)
        three_day_ok, three_day_meta = short_sellside_untaken(ctx, side, 3)

        components = {
            "mss15": bool(mss_ok),
            "no_opposing_fvg15": bool(no_opp_ok),
            "directional_fvg1m": bool(dir_fvg_ok),
            "midvol": bool(midvol_ok),
            "short_3d_low_untaken": bool(three_day_ok),
        }
        detail = {
            "component_results": components,
            "score": int(sum(components.values())),
            "score_denominator": 5,
            "strict_5of5": bool(all(components.values())),
            "short_3d_low_is_na_passthrough_for_longs": side == "long",
            "mss15_detail": mss_meta,
            "no_opposing_fvg15_detail": no_opp_meta,
            "directional_fvg1m_detail": dir_fvg_meta,
            "midvol_detail": midvol_meta,
            "short_3d_low_detail": three_day_meta,
        }
        return components, detail

    def _confluence_allows(self, ctx, side):
        components, detail = self._score_components(ctx, side)

        if side == "long":
            passed = components["mss15"] and components["no_opposing_fvg15"]
            detail.update({
                "direction_rule": "B_long_mss15_and_no_opposing_fvg15",
                "minimum_score": None,
            })
        else:
            passed = int(detail["score"]) >= 4
            detail.update({
                "direction_rule": "C_short_score_at_least_4_of_5",
                "minimum_score": 4,
            })

        return bool(passed), detail
