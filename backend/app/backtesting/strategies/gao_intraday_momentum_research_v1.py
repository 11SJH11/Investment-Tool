"""Gao-Han-Li-Zhou market intraday momentum — Ledger research v1.

Research basis
--------------
Gao, Han, Li & Zhou, "Market Intraday Momentum", Journal of Financial Economics
129(2), 2018.

Baseline implemented here:
- SPY 1-minute RTH bars.
- The first-half-hour market return is measured from the PREVIOUS trading day's
  16:00 close to the current day's 10:00 price.
- At 15:30, go long when that return is positive and short when negative.
- Hold through the last half-hour and flatten at 16:00.

The JFE paper also studies a model that adds the second-to-last half-hour return.
That extension is NOT implemented here because this file deliberately keeps the
simple first-half-hour predictor rather than inventing a coefficient/combination.

Current Ledger limitation
-------------------------
The paper baseline has no protective stop. Current Ledger EntrySignal requires one,
so this strategy uses a very wide engine-only catastrophic stop. Run with
sizing_mode='position_pct', risk_value=100 and allow_overnight=False when you want
the closest current-engine representation. R-multiple statistics are not meaningful
for this strategy until Ledger supports stopless entries.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo
import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "gao_intraday_momentum_research_v1"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "first_half_hour_minutes": 30,
    "entry_hour_et": 15,
    "entry_minute_et": 30,
    "signal_threshold_pct": 0.0,
    "engine_safety_stop_pct": 90.0,
}


def _rth(frame):
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    ts = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert(NY)
    mins = ts.dt.hour * 60 + ts.dt.minute
    mask = (mins >= 570) & (mins < 960)
    out = out.loc[mask].copy()
    ts = ts.loc[mask]
    out["_date"] = ts.dt.date.values
    out["_minute_number"] = (mins.loc[mask] - 570 + 1).astype(int).values
    return out.reset_index(drop=True)


def _safety_stop(reference, direction, pct):
    f = pct / 100.0
    return max(1e-9, reference * (1 - f)) if direction == "long" else reference * (1 + f)


@strategy_registry.register
class GaoIntradayMomentumResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="Gao Intraday Momentum · research v1",
        description=(
            "Peer-reviewed SPY intraday momentum: previous close -> first-half-hour "
            "return determines the 15:30-16:00 direction."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research",
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("first_half_hour_minutes", "Opening signal window · minutes", "int", 30, 5, 120, 5),
            ParameterSpec("entry_hour_et", "Entry hour ET", "int", 15, 9, 15, 1),
            ParameterSpec("entry_minute_et", "Entry minute ET", "int", 30, 0, 59, 1),
            ParameterSpec("signal_threshold_pct", "Minimum absolute first-window return · %", "float", 0.0, 0.0, 5.0, 0.05,
                          help="0 matches the sign-only baseline."),
            ParameterSpec("engine_safety_stop_pct", "Engine-only catastrophic stop · %", "float", 90.0, 20.0, 99.0, 1.0),
        ),
        risk_management={
            "Entry": "15:30 ET next-bar entry from sign of previous-close-to-10:00 return.",
            "Exit": "Force flat at 16:00 via BacktestConfig allow_overnight=False.",
            "Stop": "No paper stop; wide engine-only stop is present solely because current Ledger requires one.",
        },
        source_file="backend/app/backtesting/strategies/gao_intraday_momentum_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown Gao intraday momentum parameter")
        super().__init__(**params)
        self._traded_dates = set()

    def reset(self):
        self._traded_dates = set()

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("Gao intraday momentum v1 requires primary timeframe 1m")
        if ctx.position is not None:
            return None

        bars = _rth(ctx.bars("1m", count=1200))
        if bars.empty:
            return None

        today_date = bars.iloc[-1]["_date"]
        if today_date in self._traded_dates:
            return None

        today = bars.loc[bars["_date"] == today_date].copy()
        if today.empty:
            return None

        current_ts = pd.Timestamp(today.iloc[-1]["timestamp"])
        current_et = current_ts.tz_convert(NY) if current_ts.tzinfo else current_ts.tz_localize("UTC").tz_convert(NY)
        # A bar timestamp is its START. To fill at 15:30, emit after the 15:29 bar closes.
        entry_hour = int(self.params["entry_hour_et"])
        entry_minute = int(self.params["entry_minute_et"])
        desired_start_minutes = entry_hour * 60 + entry_minute - 1
        if current_et.hour * 60 + current_et.minute != desired_start_minutes:
            return None

        dates = list(pd.unique(bars["_date"]))
        idx = dates.index(today_date)
        if idx < 1:
            return None
        prev = bars.loc[bars["_date"] == dates[idx - 1]].copy()
        if prev.empty:
            return None

        prev_close = float(prev.iloc[-1]["close"])
        first_minutes = int(self.params["first_half_hour_minutes"])
        signal_rows = today.loc[today["_minute_number"] == first_minutes]
        if signal_rows.empty or prev_close <= 0:
            return None
        first_window_close = float(signal_rows.iloc[-1]["close"])
        ret = first_window_close / prev_close - 1.0

        threshold = float(self.params["signal_threshold_pct"]) / 100.0
        if abs(ret) <= threshold:
            return None
        side = "long" if ret > 0 else "short"
        allowed = str(self.params["direction"])
        if allowed != "both" and side != allowed:
            return None

        reference = float(ctx.current_bar["close"])
        stop = _safety_stop(reference, side, float(self.params["engine_safety_stop_pct"]))
        self._traded_dates.add(today_date)

        return EntrySignal(
            direction=side,
            stop_loss=stop,
            take_profit=None,
            reason="gao_first_half_hour_momentum",
            metadata={
                "paper": "Gao_Han_Li_Zhou_2018",
                "session_date": str(today_date),
                "previous_close": prev_close,
                "first_window_close": first_window_close,
                "first_window_return": ret,
                "first_window_minutes": first_minutes,
                "entry_time_et": f"{entry_hour:02d}:{entry_minute:02d}",
                "paper_has_no_stop": True,
            },
        )
