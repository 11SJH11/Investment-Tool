from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd


NEW_YORK = ZoneInfo("America/New_York")
VALID_SESSIONS = {"regular", "extended", "24h"}
_INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}


def prepare_chart_bars(
    frame: pd.DataFrame,
    timeframe: str,
    session: str,
    *,
    session_profile: str = "us_equity",
) -> tuple[pd.DataFrame, str]:
    """Prepare canonical chart bars for equities, futures and OANDA-style 24h markets.

    US equities retain the Phase 6.1 New York regular/extended filtering. Futures
    and spot-metal feeds are *not* passed through equity hours. When Replay gives
    us canonical 1-minute bars, larger bars are aligned from the market's session
    anchor (18:00 ET futures, 17:00 ET OANDA-style FX/metals) so timeframe switches
    remain deterministic.
    """
    if frame.empty or timeframe in {"1d", "1w"}:
        return frame.copy(), "provider_native"
    if session not in VALID_SESSIONS:
        raise ValueError(f"Unsupported chart session: {session}")
    duration = _INTRADAY_MINUTES.get(timeframe)
    if duration is None:
        raise ValueError(f"Unsupported intraday chart timeframe: {timeframe}")

    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)

    if session_profile != "us_equity":
        source_minutes = _infer_source_minutes(working)
        if duration == 1 or source_minutes >= duration:
            return working.sort_values("timestamp").reset_index(drop=True), "provider_native_24h"
        anchor_minute = 18 * 60 if session_profile == "futures_24h" else 17 * 60
        local = working["timestamp"].dt.tz_convert(NEW_YORK)
        minute_of_day = local.dt.hour * 60 + local.dt.minute
        working["_session_date"] = (local - pd.to_timedelta(anchor_minute, unit="m")).dt.date
        working["_slot"] = (((minute_of_day - anchor_minute) % 1440) // duration).astype(int)
        result = _aggregate(working)
        return result, f"{session_profile}_aligned_from_{source_minutes}m"

    local = working["timestamp"].dt.tz_convert(NEW_YORK)
    minutes = local.dt.hour * 60 + local.dt.minute
    if session == "24h":
        start_minute, end_minute = 0, 1440
    else:
        start_minute, end_minute = (570, 960) if session == "regular" else (240, 1200)
    working = working[(minutes >= start_minute) & (minutes < end_minute)].copy()
    if working.empty:
        return working, "session_filtered"

    source_minutes = _infer_source_minutes(working)
    if duration == 1 or source_minutes >= duration:
        return working.sort_values("timestamp").reset_index(drop=True), "session_filtered"

    local = working["timestamp"].dt.tz_convert(NEW_YORK)
    minute_of_day = local.dt.hour * 60 + local.dt.minute
    working["_session_date"] = local.dt.date
    working["_slot"] = ((minute_of_day - start_minute) // duration).astype(int)
    result = _aggregate(working)
    return result, f"session_aligned_from_{source_minutes}m"


def _aggregate(working: pd.DataFrame) -> pd.DataFrame:
    grouped = working.sort_values("timestamp").groupby(["_session_date", "_slot"], sort=True)
    aggregations = {
        "timestamp": ("timestamp", "first"),
        "open": ("open", "first"),
        "high": ("high", "max"),
        "low": ("low", "min"),
        "close": ("close", "last"),
        "volume": ("volume", "sum"),
    }
    if "source_contract" in working.columns:
        aggregations["source_contract"] = ("source_contract", "last")
    return grouped.agg(**aggregations).reset_index(drop=True)


def _infer_source_minutes(frame: pd.DataFrame) -> int:
    if len(frame) < 2:
        return 1
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).sort_values()
    diffs = timestamps.diff().dropna().dt.total_seconds().div(60)
    positive = diffs[diffs > 0]
    if positive.empty:
        return 1
    return max(1, int(round(float(positive.median()))))
