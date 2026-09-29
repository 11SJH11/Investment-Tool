"""
Ledger research strategy: Open-Session ATR Breakout.

Independent research implementation inspired by the public TradingView idea:
define breakout lines as a percentage of a completed daily ATR away from a
session opening price, then trade a confirmed intraday breakout.

The original public description does not fully specify every risk/exit detail,
so stop/target behaviour below is explicit Ledger research logic rather than a
claim of exact Pine parity.

The common Ledger engine remains responsible for fills, sizing, costs and P&L.
"""

from datetime import time
from zoneinfo import ZoneInfo

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


NY = ZoneInfo("America/New_York")

_TIMEFRAMES = {
    0: "1m",
    1: "5m",
    2: "15m",
    3: "30m",
    4: "1h",
}


def _signal_tf(params):
    return _TIMEFRAMES.get(int(params.get("signal_timeframe_code", 2)), "15m")


def _et_timestamp(ts):
    if getattr(ts, "tzinfo", None) is None:
        # Ledger stores timestamps as UTC; naive input is treated as UTC defensively.
        from datetime import timezone
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(NY)


def _minutes(h, m):
    return int(h) * 60 + int(m)


@strategy_registry.register
class OpenSessionATRBreakoutResearchV1(Strategy):
    spec = StrategySpec(
        key="open_session_atr_breakout_research_v1",
        name="Open-Session ATR Breakout · research v1",
        description=(
            "Session open +/- a fraction of completed daily ATR. A completed intraday "
            "close beyond a band triggers the first trade attempt of the session."
        ),
        defaults={
            "signal_timeframe_code": 2,   # 0=1m,1=5m,2=15m,3=30m,4=1h
            "daily_atr_length": 14,
            "breakout_atr_fraction": 0.10,
            "session_start_hour_et": 9,
            "session_start_minute_et": 30,
            "session_end_hour_et": 16,
            "session_end_minute_et": 0,
            "stop_mode": 0,               # 0=session open, 1=opposite band, 2=1 ATR from signal close
            "target_r": 2.0,
        },
        timeframes=("1m", "5m", "15m", "30m", "1h", "1d"),
        parameters=(
            ParameterSpec("signal_timeframe_code", "Signal TF code", "int", 2, 0, 4, 1),
            ParameterSpec("daily_atr_length", "Daily ATR length", "int", 14, 5, 50, 1),
            ParameterSpec("breakout_atr_fraction", "Daily ATR breakout fraction", "float", 0.10, 0.01, 1.00, 0.01),
            ParameterSpec("session_start_hour_et", "Session start hour ET", "int", 9, 0, 23, 1),
            ParameterSpec("session_start_minute_et", "Session start minute ET", "int", 30, 0, 59, 1),
            ParameterSpec("session_end_hour_et", "Session end hour ET", "int", 16, 0, 23, 1),
            ParameterSpec("session_end_minute_et", "Session end minute ET", "int", 0, 0, 59, 1),
        ),
        research_parameters=(
            ParameterSpec("stop_mode", "Stop mode (0=open,1=opposite,2=ATR)", "int", 0, 0, 2, 1),
            ParameterSpec("target_r", "Target R", "float", 2.0, 0.5, 8.0, 0.25),
        ),
        risk_management={
            "Initial stop": "Research-selectable: session open, opposite band, or one daily ATR from signal close.",
            "Initial target": "Fixed R multiple from the signal reference and selected stop.",
            "Management": "No trailing or partials in v1; one trade attempt per ET session date.",
        },
        source_file="backend/app/backtesting/strategies/open_session_atr_breakout_research_v1.py",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session_date = None
        self._session_open = None
        self._upper = None
        self._lower = None
        self._attempted = False

    def _reset_for_date(self, session_date):
        self._session_date = session_date
        self._session_open = None
        self._upper = None
        self._lower = None
        self._attempted = False

    def on_bar(self, ctx):
        if ctx.position is not None:
            return None

        tf = _signal_tf(self.params)
        atr_len = int(self.params["daily_atr_length"])
        atr_fraction = float(self.params["breakout_atr_fraction"])
        start_h = int(self.params["session_start_hour_et"])
        start_m = int(self.params["session_start_minute_et"])
        end_h = int(self.params["session_end_hour_et"])
        end_m = int(self.params["session_end_minute_et"])
        stop_mode = int(self.params.get("stop_mode", 0))
        target_r = float(self.params.get("target_r", 2.0))

        now_et = _et_timestamp(ctx.current_time)
        session_date = now_et.date()
        if self._session_date != session_date:
            self._reset_for_date(session_date)

        minute_now = _minutes(now_et.hour, now_et.minute)
        start_minute = _minutes(start_h, start_m)
        end_minute = _minutes(end_h, end_m)

        if not (start_minute <= minute_now < end_minute):
            return None

        daily_atr = ctx.indicator("atr", timeframe="1d", length=atr_len)
        if daily_atr is None:
            return None
        daily_atr = float(daily_atr)
        if not (daily_atr > 0):
            return None

        # Request enough history to reliably include today's session opening bar.
        bars = ctx.bars(tf, count=600)
        if bars is None or len(bars) == 0:
            return None

        # Identify today's first bar at the configured ET session start.
        day_rows = []
        for idx, row in bars.iterrows():
            idx_et = _et_timestamp(idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx)
            if idx_et.date() != session_date:
                continue
            mins = _minutes(idx_et.hour, idx_et.minute)
            if mins >= start_minute and mins < end_minute:
                day_rows.append((idx_et, row))

        if not day_rows:
            return None

        first_ts, first_row = day_rows[0]
        if _minutes(first_ts.hour, first_ts.minute) != start_minute:
            # Avoid silently redefining "session open" from incomplete history.
            return None

        if self._session_open is None:
            self._session_open = float(first_row["open"])
            distance = daily_atr * atr_fraction
            self._upper = self._session_open + distance
            self._lower = self._session_open - distance

        if self._attempted:
            return None

        current = bars.iloc[-1]
        close = float(current["close"])

        # Do not let the opening bar itself create a signal before the session
        # open has actually been observed and completed.
        if minute_now == start_minute:
            return None

        direction = None
        if close > self._upper:
            direction = "long"
        elif close < self._lower:
            direction = "short"
        else:
            return None

        if stop_mode == 0:
            stop = float(self._session_open)
        elif stop_mode == 1:
            stop = float(self._lower if direction == "long" else self._upper)
        else:
            stop = close - daily_atr if direction == "long" else close + daily_atr

        risk = abs(close - stop)
        if not (risk > 0):
            return None

        target = close + risk * target_r if direction == "long" else close - risk * target_r
        self._attempted = True

        return EntrySignal(
            direction,
            stop_loss=stop,
            take_profit=target,
            reason=f"open_session_atr_breakout_{direction}",
            metadata={
                "signal_tf": tf,
                "session_date_et": str(session_date),
                "session_open": float(self._session_open),
                "upper_breakout": float(self._upper),
                "lower_breakout": float(self._lower),
                "daily_atr": daily_atr,
                "daily_atr_length": atr_len,
                "breakout_atr_fraction": atr_fraction,
                "stop_mode": stop_mode,
                "target_r": target_r,
            },
        )


def test_timeframe_mapping():
    assert _TIMEFRAMES[0] == "1m"
    assert _TIMEFRAMES[2] == "15m"
    assert _TIMEFRAMES[4] == "1h"


def test_minutes_helper():
    assert _minutes(9, 30) == 570
    assert _minutes(16, 0) == 960
