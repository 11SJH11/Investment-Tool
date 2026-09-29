"""Post-run observations only; never imported by strategies or execution code."""
import math
import pandas as pd

THRESHOLDS = {"0_25": .25, "0_5": .5, "1": 1, "1_5": 1.5, "2": 2, "3": 3}


def excursion_diagnostics(trade, bars, entry_at_open=False):
    """Times are completed 1m bar bounds or exact fills, not intrabar crossings."""
    empty = {key: None for key in [
        "mfe_r", "mae_r", "mfe_price", "mae_price", "mfe_time", "mae_time",
        "time_to_mfe_minutes", "time_to_mae_minutes", *[f"time_to_{k}r" for k in THRESHOLDS]]}
    try:
        entry, stop, exit_price = (float(trade[k]) for k in ("entry_price", "stop_loss", "exit_price"))
        risk = abs(entry-stop)
        if not all(math.isfinite(v) for v in (entry, stop, exit_price, risk)) or risk <= 0:
            return empty
        start, end = pd.to_datetime(trade["entry_time"], utc=True), pd.to_datetime(trade["exit_time"], utc=True)
        if pd.isna(start) or pd.isna(end) or end < start or trade["direction"] not in ("long", "short"):
            return empty
    except (ValueError, TypeError, KeyError):
        return empty
    sign = 1 if trade["direction"] == "long" else -1
    observations = [(start, entry)]
    if bars is not None and not bars.empty:
        stamps = pd.to_datetime(bars.timestamp, utc=True)
        eligible = (stamps >= start) if entry_at_open else (stamps > start)
        held = bars.loc[eligible & (stamps + pd.Timedelta(minutes=1) <= end) & (stamps < end)].sort_values("timestamp")
        for row in held.itertuples():
            when = pd.to_datetime(row.timestamp, utc=True) + pd.Timedelta(minutes=1)
            for price in (row.high, row.low):
                if pd.notna(price) and math.isfinite(float(price)):
                    observations.append((when, float(price)))
    observations.append((end, exit_price))
    observations.sort(key=lambda item: item[0])
    best = max(observations, key=lambda item: sign*(item[1]-entry))
    worst = min(observations, key=lambda item: sign*(item[1]-entry))
    answer = dict(empty, mfe_r=sign*(best[1]-entry)/risk, mae_r=-sign*(worst[1]-entry)/risk)
    for name, (when, price) in (("mfe", best), ("mae", worst)):
        answer.update({f"{name}_price": price, f"{name}_time": when.isoformat(), f"time_to_{name}_minutes": (when-start).total_seconds()/60})
    for key, threshold in THRESHOLDS.items():
        answer[f"time_to_{key}r"] = next(((when-start).total_seconds()/60 for when, price in observations if sign*(price-entry)/risk >= threshold), None)
    return answer
