"""Replay-only aggregation: clip canonical source BEFORE deriving any values."""
import pandas as pd

from app.services.chart_data import _aggregate


def aggregate_revealed(frame, timeframe, session, profile):
    duration = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}[timeframe]
    working = frame.copy()
    working["timestamp"] = pd.to_datetime(working.timestamp, utc=True)
    local = working.timestamp.dt.tz_convert("America/New_York")
    anchor = (18*60 if profile == "futures_24h" else 17*60 if profile != "us_equity"
              else 570 if session == "regular" else 240 if session == "extended" else 0)
    minute = local.dt.hour*60 + local.dt.minute
    working["_session_date"] = (local - pd.to_timedelta(anchor, unit="m")).dt.date
    working["_slot"] = (((minute-anchor) % 1440)//duration).astype(int)
    result = _aggregate(working)
    # A partial last candle is deliberately available; it contains only revealed minutes.
    result["is_partial"] = False
    if len(result):
        result.loc[result.index[-1], "is_partial"] = bool((int(minute.iloc[-1])-anchor+1) % duration)
    return result
