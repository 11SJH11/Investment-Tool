"""Pre-performance-audit implementation; exact parity oracle, never production code."""
from zoneinfo import ZoneInfo
import pandas as pd
NY=ZoneInfo("America/New_York")

def normalise_1m(frame):
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return pd.DataFrame()

    out = frame.copy()
    ts = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert(NY)
    mins_clock = ts.dt.hour * 60 + ts.dt.minute
    mask = (mins_clock >= 570) & (mins_clock < 960)

    out = out.loc[mask].copy()
    ts = ts.loc[mask]
    if out.empty:
        return out

    out["_ts_et"] = ts.values
    out["_date"] = ts.dt.date.values
    out["_session_minute"] = (mins_clock.loc[mask] - 570).astype(int).values
    return out.reset_index(drop=True)
