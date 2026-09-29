"""Causal diagnostics for the ORB research variant, never the frozen baseline."""
from math import isfinite
from zoneinfo import ZoneInfo
import pandas as pd

NY = "America/New_York"
FILTERS = {
    "min_breakout_range_atr": ("breakout_range_atr", "min", None),
    # Exclusive upper bounds are deliberately separate research parameters.
    # This lets direct band experiments represent [min, max) without boundary overlap.
    "max_breakout_range_atr": ("breakout_range_atr", "max_exclusive", None),
    "min_breakout_body_ratio": ("breakout_body_ratio", "min", 1),
    "min_breakout_rvol": ("breakout_rvol", "min", None),
    "min_opening_range_rvol": ("opening_range_rvol", "min", None),
    "max_opening_range_rvol": ("opening_range_rvol", "max_exclusive", None),
    "min_atr_regime_percentile": ("daily_natr_percentile", "min", 100),
    # Kept inclusive for saved-run compatibility with the original research control.
    "max_atr_regime_percentile": ("daily_natr_percentile", "max", 100),
}
DEFAULTS = {key: -1.0 for key in FILTERS}
FIELDS = (
    "breakout_range", "prior_1m_atr14", "breakout_range_atr", "breakout_body",
    "breakout_body_ratio", "breakout_close_location", "breakout_volume",
    "same_minute_volume_median20", "breakout_rvol", "opening_range_volume",
    "opening_range_volume_median20", "opening_range_rvol", "previous_daily_atr14",
    "previous_close", "daily_natr_pct", "daily_natr_percentile",
)


def valid_ohlc(frame):
    if frame.empty:
        return False
    v = frame[["open", "high", "low", "close"]]
    return bool(v.map(lambda x: pd.notna(x) and isfinite(float(x))).all().all()
                and (frame.high >= frame[["open", "low", "close"]].max(axis=1)).all()
                and (frame.low <= frame[["open", "high", "close"]].min(axis=1)).all())


def wilder_atr(frame):
    """Seed with 14 true ranges requiring 15 closes; missing data breaks the seed."""
    values = [None] * len(frame)
    seed, atr = [], None
    rows = list(frame.itertuples())
    def valid(bar):
        v = (bar.open,bar.high,bar.low,bar.close)
        return all(pd.notna(x) and isfinite(float(x)) for x in v) and bar.high>=max(v) and bar.low<=min(v)
    for i in range(1, len(rows)):
        prev,bar = rows[i-1],rows[i]
        if not valid(prev) or not valid(bar):
            seed, atr = [], None
            continue
        tr = max(float(bar.high-bar.low), abs(float(bar.high-prev.close)), abs(float(bar.low-prev.close)))
        if atr is None:
            seed.append(tr)
            if len(seed) == 14:
                atr = sum(seed)/14
        else:
            atr = (13*atr+tr)/14
        values[i] = atr
    return values


def diagnostics(ctx, range_minutes, history=None):
    out = dict.fromkeys(FIELDS)
    out.update(orb_diagnostics_version="v1", historical_volume_sessions=0, historical_opening_range_sessions=0,
               atr_regime_sessions=0, daily_atr_source="provider_completed_daily")
    minute = ctx.bars("1m").sort_values("timestamp").reset_index(drop=True)
    if minute.empty:
        return out
    if history is not None and not history.empty:
        stamps = pd.to_datetime(history.timestamp,utc=True)
        prefix = history.loc[(stamps<pd.Timestamp(minute.iloc[0].timestamp)) &
                             (stamps+pd.Timedelta(minutes=1)<=pd.Timestamp(ctx.decision_time))]
        minute = pd.concat([prefix,minute],ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    stamps = pd.to_datetime(minute.timestamp, utc=True).dt.tz_convert(NY)
    dates = stamps.dt.date
    clock = stamps.dt.hour*60+stamps.dt.minute
    today = ctx.decision_time.astimezone(ZoneInfo(NY)).date()
    bar = minute.iloc[-1]
    width = float(bar.high-bar.low)
    out.update(breakout_range=width, breakout_body=abs(float(bar.close-bar.open)),
               breakout_body_ratio=abs(float(bar.close-bar.open))/width if width>0 else None,
               breakout_close_location=float(bar.close-bar.low)/width if width>0 else None,
               breakout_volume=float(bar.volume))
    # Wilder smoothing resets after a time gap; breakout bar is never in ATR.
    prior = minute.iloc[:-1]
    gaps = pd.to_datetime(prior.timestamp,utc=True).diff()!=pd.Timedelta(minutes=1)
    if gaps.any():
        prior = prior.loc[gaps[gaps].index[-1]:]
    if len(prior)>=15 and valid_ohlc(prior):
        ts = pd.to_datetime(prior.timestamp, utc=True)
        if (ts.diff().iloc[1:] == pd.Timedelta(minutes=1)).all() and pd.Timestamp(bar.timestamp)-ts.iloc[-1]==pd.Timedelta(minutes=1):
            out["prior_1m_atr14"] = wilder_atr(prior)[-1]
    if out["prior_1m_atr14"] and out["prior_1m_atr14"]>0:
        out["breakout_range_atr"] = width/out["prior_1m_atr14"]
    base = minute.loc[(dates==today)&(clock>=570)&(clock<570+range_minutes)]
    out["opening_range_volume"] = float(base.volume.sum()) if len(base)==range_minutes else None
    try:
        daily = ctx.bars("1d").sort_values("timestamp").reset_index(drop=True)
    except KeyError:
        return out
    if daily.empty:
        return out
    # Equity frames are normalized by the service to the dated NY session open.
    # Dated futures daily bars retain provider session labels supplied below.
    daily_dates = (pd.to_datetime(daily.session_date).dt.date if "session_date" in daily
                   else pd.to_datetime(daily.timestamp, utc=True).dt.tz_convert(NY).dt.date)
    daily = daily.loc[daily_dates < today].copy()
    daily_dates = daily_dates.loc[daily_dates < today]
    if daily.empty or daily_dates.duplicated().any():
        return out
    observed_days = set(dates.loc[(dates<today)&(clock>=570)&(clock<960)])
    if any(day>=daily_dates.iloc[0] and day not in set(daily_dates) for day in observed_days):
        # A known intraday session missing from daily history must not compress
        # the ATR or 20-session reference window.
        return out
    atrs = wilder_atr(daily)
    closes = daily.close.tolist()
    natr = [100*a/float(c) if a is not None and pd.notna(c) and isfinite(float(c)) and c>0 else None for a,c in zip(atrs,closes)]
    last = daily.iloc[-1]
    out["previous_close"] = float(last.close) if pd.notna(last.close) and isfinite(float(last.close)) else None
    out["previous_daily_atr14"], out["daily_natr_pct"] = atrs[-1], natr[-1]
    comparison = natr[-61:-1]
    out["atr_regime_sessions"] = sum(v is not None for v in comparison)
    if len(comparison)==60 and all(v is not None for v in comparison) and natr[-1] is not None:
        out["daily_natr_percentile"] = 100*sum(v<=natr[-1] for v in comparison)/60
    # Daily provider observations define session membership: never backfill a
    # missing minute/session with an older intraday observation.
    history = daily_dates.tail(20).tolist()
    if len(history)!=20:
        return out
    minute_volumes, range_volumes = [], []
    for day in history:
        matched = minute.loc[(dates==day)&(clock==int(clock.iloc[-1]))]
        opening = minute.loc[(dates==day)&(clock>=570)&(clock<570+range_minutes)]
        def volumes_valid(rows, count):
            ts = pd.to_datetime(rows.timestamp,utc=True)
            return (len(rows)==count and rows.timestamp.nunique()==count
                    and (ts.dt.second==0).all() and (ts.dt.microsecond==0).all() and (ts.dt.nanosecond==0).all()
                    and rows.volume.map(lambda v: pd.notna(v) and isfinite(float(v)) and v>=0).all())
        if volumes_valid(matched,1):
            minute_volumes.append(float(matched.iloc[0].volume))
        if volumes_valid(opening,range_minutes):
            range_volumes.append(float(opening.volume.sum()))
    out["historical_volume_sessions"] = len(minute_volumes)
    out["historical_opening_range_sessions"] = len(range_volumes)
    for values, median_key, rvol_key, numerator in (
        (minute_volumes,"same_minute_volume_median20","breakout_rvol",out["breakout_volume"]),
        (range_volumes,"opening_range_volume_median20","opening_range_rvol",out["opening_range_volume"])):
        if len(values)==20:
            median = float(pd.Series(values).median())
            out[median_key] = median
            out[rvol_key] = numerator/median if median>0 and numerator is not None else None
    return out


def rejection(params, metadata):
    for key,(metric,side,_) in FILTERS.items():
        bound = params[key]
        if bound < 0:
            continue
        value = metadata[metric]
        if value is None or not isfinite(value):
            return f"{key}_unavailable"
        if ((side=="min" and value<bound)
                or (side=="max" and value>bound)
                or (side=="max_exclusive" and value>=bound)):
            return f"{key}_filter"
    return None
