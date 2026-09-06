from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd


NEW_YORK = ZoneInfo("America/New_York")
VALID_SESSIONS = {"regular", "extended"}
_INTRADAY_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}


def prepare_chart_bars(frame: pd.DataFrame, timeframe: str, session: str) -> tuple[pd.DataFrame, str]:
    """Filter/aggregate US-equity bars using explicit New York session boundaries.

    Timestamps remain UTC in storage/API output. Session logic is applied in
    America/New_York so DST is handled by the standard timezone database.

    When the caller supplies 1-minute source bars, every supported intraday
    timeframe is session-aligned from that same canonical series. This is used by
    Replay so switching 1m/5m/15m/30m/1h/4h cannot silently mix vendor-native
    aggregations with different boundaries.
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
    local = working["timestamp"].dt.tz_convert(NEW_YORK)
    minutes = local.dt.hour * 60 + local.dt.minute
    start_minute, end_minute = (570, 960) if session == "regular" else (240, 1200)
    working = working[(minutes >= start_minute) & (minutes < end_minute)].copy()
    if working.empty:
        return working, "session_filtered"

    source_minutes = _infer_source_minutes(working)
    # If the caller already supplied bars at the requested cadence, only session
    # filtering is needed. This preserves the normal Research/backtest path while
    # Replay (which supplies 1m bars) is aggregated consistently below.
    if duration == 1 or source_minutes >= duration:
        return working.sort_values("timestamp").reset_index(drop=True), "session_filtered"

    # Align every larger intraday bar to the selected exchange-session open.
    # This makes 5m start at 09:30 ET (regular), 15m at 09:30, 1h at 09:30,
    # etc., while extended-hours bars align from 04:00 ET.
    local = working["timestamp"].dt.tz_convert(NEW_YORK)
    minute_of_day = local.dt.hour * 60 + local.dt.minute
    working["_session_date"] = local.dt.date
    working["_slot"] = ((minute_of_day - start_minute) // duration).astype(int)

    grouped = working.sort_values("timestamp").groupby(["_session_date", "_slot"], sort=True)
    result = grouped.agg(
        timestamp=("timestamp", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index(drop=True)
    return result, f"session_aligned_from_{source_minutes}m"


def _infer_source_minutes(frame: pd.DataFrame) -> int:
    if len(frame) < 2:
        return 1
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).sort_values()
    diffs = timestamps.diff().dropna().dt.total_seconds().div(60)
    positive = diffs[diffs > 0]
    if positive.empty:
        return 1
    return max(1, int(round(float(positive.median()))))
