from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from app.indicators.registry import indicator_registry
from app.backtesting.models import Position


_TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}


class StrategyContext:
    """Point-in-time view passed to a strategy.

    The context never exposes a bar that has not completed by ``decision_time``.
    That is the core no-lookahead boundary used by every strategy plugin.
    """

    def __init__(
        self,
        *,
        symbol: str,
        primary_timeframe: str,
        decision_time: datetime,
        frames: dict[str, pd.DataFrame],
        position: Position | None,
        equity: float,
        indicator_cache: dict | None = None,
    ):
        self.symbol = symbol
        self.primary_timeframe = primary_timeframe
        self.decision_time = decision_time
        self._frames = frames
        self.position = position
        self.equity = equity
        self._indicator_cache = indicator_cache if indicator_cache is not None else {}

    @property
    def current_bar(self) -> pd.Series:
        bars = self.bars(self.primary_timeframe, count=1)
        if bars.empty:
            raise RuntimeError("No completed primary bar is available")
        return bars.iloc[-1]

    def bars(self, timeframe: str | None = None, count: int | None = None) -> pd.DataFrame:
        timeframe = timeframe or self.primary_timeframe
        try:
            frame = self._frames[timeframe]
        except KeyError as exc:
            raise KeyError(f"Strategy requested unloaded timeframe '{timeframe}'") from exc
        available = _completed_bars(frame, timeframe, self.decision_time)
        if count is not None:
            available = available.tail(max(0, int(count)))
        return available.copy()

    def indicator(self, key: str, *, timeframe: str | None = None, **params):
        timeframe = timeframe or self.primary_timeframe
        available = self.bars(timeframe)
        indicator = indicator_registry.create(key)
        # Registered indicators may opt into full-frame caching only when they are
        # explicitly declared causal (value[t] cannot depend on future rows).
        if indicator.spec.causal:
            cache_key = (key, timeframe, tuple(sorted((k, repr(v)) for k, v in params.items())))
            if cache_key not in self._indicator_cache:
                self._indicator_cache[cache_key] = indicator.calculate(self._frames[timeframe].copy(), **params)
            full = self._indicator_cache[cache_key]
            return full.iloc[: len(available)].copy()
        return indicator.calculate(available, **params)


def timeframe_delta(timeframe: str) -> timedelta:
    try:
        return timedelta(minutes=_TIMEFRAME_MINUTES[timeframe])
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe '{timeframe}'") from exc


def _completed_bars(frame: pd.DataFrame, timeframe: str, decision_time: datetime) -> pd.DataFrame:
    if frame.empty:
        return frame
    working = frame.copy()
    timestamps = pd.to_datetime(working["timestamp"], utc=True)
    cutoff = pd.Timestamp(decision_time)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    # Timestamps represent bar starts. Only expose a bar after its nominal duration
    # has elapsed. Session-filtered 1h/4h bars follow the same contract.
    available_at = (pd.to_datetime(working["available_at"], utc=True)
                    if "available_at" in working else timestamps + timeframe_delta(timeframe))
    completed = available_at <= cutoff
    return working.loc[completed].reset_index(drop=True)
