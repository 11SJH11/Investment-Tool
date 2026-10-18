"""D6 + middle 50% same-time-of-day 1m volatility percentile."""
import math
import numpy as np
import pandas as pd
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.vwap_confluence_common import FrozenD6ConfluenceBase, make_spec, _rth

KEY = "vwap_d6_midvol_research_v1"

@strategy_registry.register
class VwapD6MidVolResearchV1(FrozenD6ConfluenceBase):
    CONFLUENCE_ID = "tod_1m_volatility_percentile_middle_25_75"
    spec = make_spec(
        KEY, "VWAP D6 + middle volatility · research v1",
        "Frozen D6 VWAP baseline. Entry/reversal requires current 1m true-range volatility to sit in the 25th-75th percentile versus up to 60 prior RTH sessions at the same minute.",
        "backend/app/backtesting/strategies/vwap_d6_midvol_research_v1.py",
        "Require 25th <= same-time-of-day 1m volatility percentile < 75th; exits remain frozen E2.",
    )

    def reset(self):
        super().reset()
        self._tod_cache_date = None
        self._tod_prior = {}

    def _build_prior(self, bars, current_date):
        dates = [d for d in list(dict.fromkeys(bars["session_date"].tolist())) if d < current_date][-60:]
        prior = {}
        for date in dates:
            session = bars.loc[bars["session_date"] == date].copy()
            if session.empty:
                continue
            tr_bps = session["tr_bps"].astype(float).to_numpy()
            for minute, value in zip(session["session_minute"].astype(int), tr_bps):
                if math.isfinite(float(value)):
                    prior.setdefault(int(minute), []).append(float(value))
        self._tod_prior = prior
        self._tod_cache_date = current_date

    def _confluence_allows(self, ctx, side):
        bars = _rth(ctx.bars("1m", count=26000))
        if bars.empty:
            return False, {"status": "missing_1m_history"}
        current_date = bars.iloc[-1]["session_date"]
        if self._tod_cache_date != current_date:
            self._build_prior(bars, current_date)
        current = bars.loc[bars["session_date"] == current_date].reset_index(drop=True)
        if current.empty:
            return False, {"status": "missing_current_session"}
        row = current.iloc[-1]
        minute = int(row["session_minute"])
        values = np.asarray(self._tod_prior.get(minute, []), dtype=float)
        if len(values) < 10:
            return False, {"status": "insufficient_prior_same_minute_sessions", "history_sessions": int(len(values))}
        this = float(row["tr_bps"]) if math.isfinite(float(row["tr_bps"])) else math.nan
        percentile = float(np.mean(values <= this)) if math.isfinite(this) else math.nan
        passed = math.isfinite(percentile) and 0.25 <= percentile < 0.75
        return passed, {"volatility_percentile": percentile, "history_sessions": int(len(values)), "lower": 0.25, "upper": 0.75}
