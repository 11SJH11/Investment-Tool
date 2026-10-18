"""Combined VWAP D6 confluence research children.

Research-only development strategies built from the already-tested isolated
confluences.  They preserve the frozen D6/X25/E2/EMA20 VWAP parent and alter
entry/reversal eligibility only.

Registered strategies
---------------------
1) vwap_d6_score4of5_research_v1
   Require at least four of the five previously analysed confluence conditions.

2) vwap_d6_score5of5_research_v1
   Strict challenger requiring all five conditions.

3) vwap_d6_mss15_no_opp_fvg15_research_v1
   Simple two-condition control requiring both 15m MSS and no unresolved
   opposing 15m FVG.

Important score semantics
-------------------------
The fifth condition (prior-three-session low untaken) is intentionally short-only.
For LONG signals it is treated as a pass, matching the prior 4-of-5 diagnostic
analysis.  Therefore:
- score >= 4 on a long means at least 3 of the 4 universally applicable
  confluences pass, plus the short-only N/A passthrough;
- score == 5 on a long means all 4 universal confluences pass;
- shorts genuinely score all 5 conditions.

Do not reinterpret these development runs as unseen validation.
"""
from __future__ import annotations

from dataclasses import replace
import math

import numpy as np

from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import (
    FrozenD6ConfluenceBase,
    _rth,
    directional_fvg1m_5bps_30m,
    make_spec,
    mss15_rolling_s2,
    no_unfilled_opposing_fvg15,
    short_sellside_untaken,
)

SOURCE = "backend/app/backtesting/strategies/vwap_d6_combined_confluences_research_v1.py"


def _middle_volatility_25_75(instance, ctx) -> tuple[bool, dict]:
    """Exact middle-volatility logic used by vwap_d6_midvol_research_v1."""
    bars = _rth(ctx.bars("1m", count=26000))
    if bars.empty:
        return False, {"status": "missing_1m_history"}

    current_date = bars.iloc[-1]["session_date"]
    if instance._tod_cache_date != current_date:
        dates = [
            d for d in list(dict.fromkeys(bars["session_date"].tolist()))
            if d < current_date
        ][-60:]
        prior: dict[int, list[float]] = {}
        for date in dates:
            session = bars.loc[bars["session_date"] == date]
            if session.empty:
                continue
            for minute, value in zip(
                session["session_minute"].astype(int),
                session["tr_bps"].astype(float),
            ):
                value = float(value)
                if math.isfinite(value):
                    prior.setdefault(int(minute), []).append(value)
        instance._tod_prior = prior
        instance._tod_cache_date = current_date

    current = bars.loc[bars["session_date"] == current_date].reset_index(drop=True)
    if current.empty:
        return False, {"status": "missing_current_session"}

    row = current.iloc[-1]
    minute = int(row["session_minute"])
    values = np.asarray(instance._tod_prior.get(minute, []), dtype=float)
    if len(values) < 10:
        return False, {
            "status": "insufficient_prior_same_minute_sessions",
            "history_sessions": int(len(values)),
        }

    this = float(row["tr_bps"])
    percentile = float(np.mean(values <= this)) if math.isfinite(this) else math.nan
    passed = math.isfinite(percentile) and 0.25 <= percentile < 0.75
    return passed, {
        "volatility_percentile": percentile,
        "history_sessions": int(len(values)),
        "lower": 0.25,
        "upper": 0.75,
    }


class _CombinedConfluenceBase(FrozenD6ConfluenceBase):
    """Shared exact definitions for the preregistered combination tests."""

    def reset(self):
        super().reset()
        self._tod_cache_date = None
        self._tod_prior: dict[int, list[float]] = {}

    def _five_components(self, ctx, side: str) -> tuple[dict[str, bool], dict]:
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
            "short_3d_low_is_na_passthrough_for_longs": side == "long",
            "mss15_detail": mss_meta,
            "no_opposing_fvg15_detail": no_opp_meta,
            "directional_fvg1m_detail": dir_fvg_meta,
            "midvol_detail": midvol_meta,
            "short_3d_low_detail": three_day_meta,
        }
        return components, detail


KEY_SCORE4 = "vwap_d6_score4of5_research_v1"


@strategy_registry.register
class VwapD6Score4of5ResearchV1(_CombinedConfluenceBase):
    CONFLUENCE_ID = "preregistered_confluence_score_at_least_4_of_5"
    spec = replace(
        make_spec(
            KEY_SCORE4,
            "VWAP D6 + confluence score >=4/5 · research v1",
            "Frozen D6 VWAP baseline. Entry/reversal requires at least four of five preregistered confluence conditions: 15m MSS, no unresolved opposing 15m FVG, recent directional 1m FVG >=5 bps, middle same-time volatility, and short-only prior-3-session low untaken.",
            SOURCE,
            "Require preregistered confluence score >=4/5; exits remain frozen E2.",
        ),
        timeframes=("1m", "15m"),
    )

    def _confluence_allows(self, ctx, side):
        _, detail = self._five_components(ctx, side)
        detail["minimum_score"] = 4
        return int(detail["score"]) >= 4, detail


KEY_SCORE5 = "vwap_d6_score5of5_research_v1"


@strategy_registry.register
class VwapD6Score5of5ResearchV1(_CombinedConfluenceBase):
    CONFLUENCE_ID = "preregistered_confluence_score_5_of_5"
    spec = replace(
        make_spec(
            KEY_SCORE5,
            "VWAP D6 + confluence score 5/5 · research v1",
            "Strict challenger to the preregistered 4-of-5 score. Entry/reversal requires all five confluence conditions.",
            SOURCE,
            "Require all 5 preregistered confluence conditions; exits remain frozen E2.",
        ),
        timeframes=("1m", "15m"),
    )

    def _confluence_allows(self, ctx, side):
        _, detail = self._five_components(ctx, side)
        detail["minimum_score"] = 5
        return int(detail["score"]) >= 5, detail


KEY_PAIR = "vwap_d6_mss15_no_opp_fvg15_research_v1"


@strategy_registry.register
class VwapD6Mss15NoOppFvg15ResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "mss15_and_no_unresolved_opposing_fvg15"
    spec = replace(
        make_spec(
            KEY_PAIR,
            "VWAP D6 + MSS15 AND no opposing FVG15 · research v1",
            "Simple combination control. Entry/reversal requires both the rolling strict-2 15m MSS proxy and no unresolved opposing rolling 15m FVG.",
            SOURCE,
            "Require MSS15 AND no unresolved opposing FVG15; exits remain frozen E2.",
        ),
        timeframes=("1m", "15m"),
    )

    def _confluence_allows(self, ctx, side):
        mss_ok, mss_meta = mss15_rolling_s2(ctx, side)
        no_opp_ok, no_opp_meta = no_unfilled_opposing_fvg15(ctx, side)
        detail = {
            "mss15": bool(mss_ok),
            "no_opposing_fvg15": bool(no_opp_ok),
            "mss15_detail": mss_meta,
            "no_opposing_fvg15_detail": no_opp_meta,
        }
        return bool(mss_ok and no_opp_ok), detail
