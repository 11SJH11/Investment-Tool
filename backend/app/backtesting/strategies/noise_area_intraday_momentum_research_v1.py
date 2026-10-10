"""Noise Area Intraday Momentum — Ledger research v1.

Research basis
--------------
Zarattini, Aziz & Barbon, "Beat the Market: An Effective Intraday Momentum
Strategy for S&P500 ETF (SPY)", SSRN 4824172.

Defaults follow the paper-style rules supplied for this Ledger project:
- SPY, 1-minute RTH bars.
- For each minute-of-session, sigma is the mean absolute move from that day's
  09:30 open over the previous 14 completed sessions.
- Upper = max(today open, previous close) * (1 + band_multiple * sigma).
- Lower = min(today open, previous close) * (1 - band_multiple * sigma).
- Session VWAP uses HLC3 * volume and resets at 09:30.
- Evaluate only every 30 minutes (09:59 close -> 10:00 next-bar fill, etc.).
- Long condition: close > upper AND close > VWAP.
- Short condition: close < lower AND close < VWAP.
- A zero/opposite signal exits the current position at Ledger's next-bar open.
- Flat at the session close should be enforced with BacktestConfig
  allow_overnight=False / force_close_time=16:00.

Important current Ledger limitations
------------------------------------
1) The paper's daily volatility-targeted sizing (2% / trailing daily vol, capped
   at 4x) cannot be applied exactly by a Strategy plugin because EntrySignal has
   no per-signal quantity/leverage override. This implementation calculates the
   paper leverage and stores it in signal metadata for audit, but Ledger's run
   configuration still owns actual sizing.
2) Ledger cannot atomically reverse at the same next-bar open. On an opposite
   half-hour signal, this strategy exits at that next open and then enters the
   new direction one minute later. Same-direction and flat transitions are causal.
3) Per-share commissions are not represented by the current fixed-per-order
   commission field, so exact paper cost replication requires a later engine patch.

This is therefore suitable for signal-rule screening and near-replication, but the
above execution differences must be fixed before claiming exact paper parity.
"""

from __future__ import annotations

from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "noise_area_intraday_momentum_research_v1"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "lookback_sessions": 14,
    "band_multiple": 1.0,
    "trade_frequency_minutes": 30,
    "target_daily_vol": 0.02,
    "paper_max_leverage": 4.0,
    "engine_safety_stop_pct": 90.0,
}


def _rth(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    stamps = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert(NY)
    mins = stamps.dt.hour * 60 + stamps.dt.minute
    mask = (mins >= 570) & (mins < 960)
    out = out.loc[mask].copy()
    stamps = stamps.loc[mask]
    out["_date"] = stamps.dt.date.values
    out["_minute_number"] = (mins.loc[mask] - 570 + 1).astype(int).values
    return out.reset_index(drop=True)


def _session_open(group: pd.DataFrame) -> float:
    return float(group.iloc[0]["open"])


def _session_close(group: pd.DataFrame) -> float:
    return float(group.iloc[-1]["close"])


def _session_vwap(group: pd.DataFrame) -> float | None:
    volume = group["volume"].astype(float)
    total = float(volume.sum())
    if total <= 0:
        return None
    tp = (group["high"].astype(float) + group["low"].astype(float) + group["close"].astype(float)) / 3.0
    return float((tp * volume).sum() / total)


def _daily_returns(groups: list[pd.DataFrame]) -> list[float]:
    closes = [_session_close(g) for g in groups]
    out = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            out.append(closes[i] / closes[i - 1] - 1.0)
    return out


def _safety_stop(reference: float, direction: str, pct: float) -> float:
    f = pct / 100.0
    if direction == "long":
        return max(1e-9, reference * (1.0 - f))
    return reference * (1.0 + f)


@strategy_registry.register
class NoiseAreaIntradayMomentumResearchV1(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="Noise Area Intraday Momentum · research v1",
        description=(
            "SPY paper-style Noise Area momentum: 14-session time-of-day bands, "
            "session VWAP confirmation, half-hour decisions, intraday only."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research",
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("lookback_sessions", "Sigma lookback sessions", "int", 14, 5, 60, 1),
            ParameterSpec("band_multiple", "Noise band multiple", "float", 1.0, 0.25, 3.0, 0.25),
            ParameterSpec("trade_frequency_minutes", "Decision frequency · minutes", "int", 30, 5, 120, 5),
            ParameterSpec("target_daily_vol", "Paper daily volatility target", "float", 0.02, 0.0025, 0.10, 0.0025,
                          help="Recorded in metadata; current Ledger Strategy API cannot apply per-signal sizing."),
            ParameterSpec("paper_max_leverage", "Paper maximum leverage", "float", 4.0, 1.0, 10.0, 0.5,
                          help="Recorded in metadata; set Ledger max leverage separately."),
            ParameterSpec("engine_safety_stop_pct", "Engine-only catastrophic stop · %", "float", 90.0, 20.0, 99.0, 1.0,
                          help="Not a paper rule. Required because current Ledger EntrySignal requires a stop."),
        ),
        risk_management={
            "Entry": "At configured half-hour checks, long above both upper Noise Area band and VWAP; short below both lower band and VWAP.",
            "Exit": "Exit when the next configured check no longer supports the current direction; force flat at 16:00 via run configuration.",
            "Sizing": "Paper leverage is calculated and recorded, but current Ledger cannot apply dynamic per-signal leverage.",
            "Safety stop": "Very wide engine-only stop; not part of the paper strategy.",
        },
        source_file="backend/app/backtesting/strategies/noise_area_intraday_momentum_research_v1.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown Noise Area parameter")
        super().__init__(**params)
        self._pending_reverse: str | None = None
        self._last_signal_date = None

    def reset(self):
        self._pending_reverse = None
        self._last_signal_date = None

    def _emit_entry(self, ctx, direction: str, meta: dict):
        reference = float(ctx.current_bar["close"])
        stop = _safety_stop(reference, direction, float(self.params["engine_safety_stop_pct"]))
        return EntrySignal(
            direction=direction,
            stop_loss=stop,
            take_profit=None,
            reason="noise_area_momentum",
            metadata=meta,
        )

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("Noise Area research v1 requires primary timeframe 1m")

        # If Ledger had to close an opposite position first, enter the pending
        # new side on the next available decision. This is one minute later than
        # an atomic paper-style reversal and is explicitly disclosed above.
        if ctx.position is None and self._pending_reverse is not None:
            side = self._pending_reverse
            self._pending_reverse = None
            return self._emit_entry(
                ctx,
                side,
                {"paper_rule": "deferred_reverse_due_to_engine_contract", "direction": side},
            )

        bars = _rth(ctx.bars("1m", count=7000))
        if bars.empty or len(bars) < 2:
            return None

        current_date = bars.iloc[-1]["_date"]
        today = bars.loc[bars["_date"] == current_date].copy()
        if today.empty:
            return None

        current = today.iloc[-1]
        minute_number = int(current["_minute_number"])
        freq = int(self.params["trade_frequency_minutes"])
        if minute_number <= 0 or minute_number % freq != 0:
            return None

        dates = list(pd.unique(bars["_date"]))
        if current_date not in dates:
            return None
        current_idx = dates.index(current_date)
        lookback = int(self.params["lookback_sessions"])
        if current_idx < lookback:
            return None

        prior_dates = dates[current_idx - lookback: current_idx]
        prior_groups = [bars.loc[bars["_date"] == d].copy() for d in prior_dates]
        if len(prior_groups) != lookback:
            return None

        same_minute_moves = []
        for g in prior_groups:
            row = g.loc[g["_minute_number"] == minute_number]
            if row.empty:
                return None
            op = _session_open(g)
            if op <= 0:
                return None
            same_minute_moves.append(abs(float(row.iloc[-1]["close"]) / op - 1.0))

        sigma = float(pd.Series(same_minute_moves).mean())
        today_open = _session_open(today)

        prev_day = bars.loc[bars["_date"] == dates[current_idx - 1]].copy()
        if prev_day.empty:
            return None
        prev_close = _session_close(prev_day)

        band_mult = float(self.params["band_multiple"])
        upper = max(today_open, prev_close) * (1.0 + band_mult * sigma)
        lower = min(today_open, prev_close) * (1.0 - band_mult * sigma)
        vwap = _session_vwap(today)
        if vwap is None:
            return None

        close = float(current["close"])
        desired = "long" if close > upper and close > vwap else "short" if close < lower and close < vwap else None

        allowed = str(self.params["direction"])
        if desired is not None and allowed != "both" and desired != allowed:
            desired = None

        # Paper-style daily leverage diagnostic from prior daily returns.
        hist_dates = dates[:current_idx]
        hist_groups = [bars.loc[bars["_date"] == d].copy() for d in hist_dates[-(lookback + 1):]]
        returns = _daily_returns(hist_groups)
        daily_vol = float(pd.Series(returns[-lookback:]).std(ddof=1)) if len(returns) >= lookback else float("nan")
        target_vol = float(self.params["target_daily_vol"])
        max_lev = float(self.params["paper_max_leverage"])
        paper_leverage = max_lev if not isfinite(daily_vol) or daily_vol <= 0 else min(max_lev, target_vol / daily_vol)

        meta = {
            "paper": "Zarattini_Aziz_Barbon_noise_area",
            "session_date": str(current_date),
            "minute_number": minute_number,
            "sigma_open": sigma,
            "upper_band": upper,
            "lower_band": lower,
            "vwap": vwap,
            "signal_close": close,
            "today_open": today_open,
            "previous_close": prev_close,
            "desired_direction": desired,
            "daily_vol_estimate": daily_vol,
            "paper_target_daily_vol": target_vol,
            "paper_max_leverage": max_lev,
            "paper_leverage": paper_leverage,
            "sizing_limitation": "metadata_only_current_ledger_api",
        }

        if ctx.position is not None:
            if desired == ctx.position.direction:
                return None
            if desired is not None:
                self._pending_reverse = desired
            return ExitSignal("noise_area_signal_exit")

        if desired is None:
            return None
        return self._emit_entry(ctx, desired, meta)
