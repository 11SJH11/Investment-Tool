"""Daily data contract and post-run diagnostics; no execution/account arithmetic."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
BIAS_WARNING = "Historical universe may contain survivorship bias."


def completed_daily_frame(frame, end):
    result = frame.copy()
    if result.empty:
        return result
    dates = pd.to_datetime(result.timestamp, utc=True).dt.tz_convert(NY).dt.date
    if dates.duplicated().any():
        raise ValueError("Daily equity data contains duplicate session dates")
    result["timestamp"] = pd.to_datetime([datetime.combine(d, time(9, 30), NY) for d in dates], utc=True)
    result["available_at"] = pd.to_datetime([datetime.combine(d+timedelta(days=1), time.min, NY) for d in dates], utc=True)
    result = result.loc[result.available_at <= pd.Timestamp(end)].sort_values("timestamp").reset_index(drop=True)
    if result.empty:
        return result
    fields = result[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    if (fields.isna().any().any() or not fields.map(lambda x: float("-inf") < x < float("inf")).all().all()
            or (fields[["open", "high", "low", "close"]] <= 0).any().any() or (fields.volume < 0).any()
            or (fields.high < fields[["open", "close", "low"]].max(axis=1)).any()
            or (fields.low > fields[["open", "close", "high"]].min(axis=1)).any()):
        raise ValueError("Daily equity data contains invalid OHLCV observations")
    result[fields.columns] = fields
    return result


def annotate_result(result, frames, params):
    result["data"]["warnings"] = [
        BIAS_WARNING,
        "Selected tickers only; no historical universe membership or delisting returns. No missing sessions are synthesized.",
        "Provider-native daily OHLCV; modeled open 09:30 NY, confirmation after the full NY date. Intrabar exit timestamps are session labels.",
        "First 250 prior observations are warm-up (or more when configured); selected dates include this warm-up.",
        "MFE/MAE exclude unknown exit-bar extremes and are conservative lower bounds.",
    ]
    result["data"]["universe_type"] = "user_selected_current_symbols_not_point_in_time"
    result["data"]["portfolio_scope"] = "Explicit symbols; shared capital, configured exposure and position limits; simultaneous fills ordered alphabetically."
    result["strategy"]["params"] = dict(params)
    result["execution_model"]["daily_availability"] = "following_New_York_midnight"
    by_setup = {}
    for trade in result["trades"]:
        frame = frames[trade["symbol"]]["1d"]
        entry, exit = pd.Timestamp(trade["entry_time"]), pd.Timestamp(trade["exit_time"])
        held = frame.loc[(frame.timestamp >= entry) & (frame.timestamp < exit)]
        # Intrabar protective exits carry the bar's open timestamp: exclude that
        # bar. End-of-data uses its completed timestamp, so includes its range.
        prices = [trade["entry_price"], trade["exit_price"]]
        high = max([*prices, *held.high.tolist()])
        low = min([*prices, *held.low.tolist()])
        risk = trade["entry_price"] - trade["stop_loss"]
        exit_bar = frame.loc[frame.timestamp <= exit].iloc[-1]
        trade["metadata"].update({
            "entry": trade["entry_price"], "stop": trade["stop_loss"], "target": trade["take_profit"],
            "risk_per_share": risk, "stop_distance_pct": 100*risk/trade["entry_price"],
            "result_r": trade["r_multiple"], "mfe_r_lower_bound": (high-trade["entry_price"])/risk,
            "mae_r_lower_bound": (trade["entry_price"]-low)/risk,
            "bars_in_trade": int(((frame.timestamp >= entry) & (frame.timestamp <= exit)).sum()),
            "days_in_trade": (exit.tz_convert(NY).date()-entry.tz_convert(NY).date()).days,
            "exit": trade["exit_price"], "exit_reason": trade["exit_reason"],
            "exit_bar_time": pd.Timestamp(exit_bar.timestamp).isoformat(),
        })
        by_setup[(trade["symbol"], trade["metadata"]["confirmed_at"])] = trade
    for setup in result["setups"]:
        meta = setup["metadata"]
        trade = by_setup.get((setup["symbol"], meta["confirmed_at"]))
        outcome = {
            "setup_detected": True, "breakout_confirmed": True,
            "entered": setup["status"] == "filled", "next_open": setup.get("next_open"),
            "entry_distance_pivot_pct": (100*(setup["next_open"] / meta["pivot"]-1)
                                         if setup.get("next_open") is not None else None),
            "rejection_reason": setup.get("resolution_reason"),
            "entry": None, "stop": setup.get("stop_loss"), "target": None,
            "candidate_entry": setup.get("candidate_entry"),
            "risk_per_share": setup.get("risk_per_share"), "stop_distance_pct": setup.get("stop_distance_pct"),
            "result_r": None, "mfe_r_lower_bound": None, "mae_r_lower_bound": None,
            "bars_in_trade": None, "days_in_trade": None, "exit_reason": None,
        }
        if trade:
            outcome.update({k: trade["metadata"][k] for k in (
                "entry", "stop", "target", "risk_per_share", "stop_distance_pct", "result_r",
                "mfe_r_lower_bound", "mae_r_lower_bound", "bars_in_trade", "days_in_trade", "exit_reason", "exit")})
            trade["metadata"].update({k: outcome[k] for k in ("entered", "next_open", "entry_distance_pivot_pct", "rejection_reason")})
        setup["outcome"] = outcome
