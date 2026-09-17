"""Post-simulation diagnostics; never an input to strategy eligibility."""
import pandas as pd


def annotate_intraday(result, frames):
    outcomes = {}
    for trade in result["trades"]:
        entry, exit_price = float(trade["entry_price"]), float(trade["exit_price"])
        risk = abs(entry - float(trade["stop_loss"]))
        bars = frames[trade["symbol"]]["1m"]
        stamps = pd.to_datetime(bars.timestamp, utc=True)
        start, end = pd.Timestamp(trade["entry_time"]), pd.Timestamp(trade["exit_time"])
        held = bars.loc[(stamps >= start) & (stamps < end)]
        high = max(entry, exit_price, float(held.high.max()) if len(held) else entry)
        low = min(entry, exit_price, float(held.low.min()) if len(held) else entry)
        long = trade["direction"] == "long"
        outcome = dict(entry=entry, stop=trade["stop_loss"], target=trade["take_profit"],
            exit=exit_price, result_r=trade["r_multiple"], exit_reason=trade["exit_reason"],
            mfe_r=(high-entry if long else entry-low)/risk if risk else None,
            mae_r=(entry-low if long else high-entry)/risk if risk else None,
            excursion_measurement="lower_bound_excluding_exit_bar", bars_in_trade=len(held),
            minutes_in_trade=(end-start).total_seconds()/60)
        trade["metadata"].update(outcome)
        outcomes[(trade["symbol"], trade["metadata"].get("confirmed_at"))] = outcome
    for setup in result["setups"]:
        meta = setup["metadata"]
        meta.update(setup_entered=setup["status"] == "filled",
                    rejection_reason=setup.get("resolution_reason") if setup["status"] != "filled" else None)
        meta.update(outcomes.get((setup["symbol"], meta.get("confirmed_at")), {}))
    result.setdefault("data", {})["warnings"] = [
        "Requires continuous 1m observations from 09:30 New York; incomplete sessions produce no signals.",
        "Cash-session window is not an early-close/holiday calendar. Entry expiry does not force position exits.",
        "Volume is provider-specific; IEX is not consolidated market volume. Futures coverage requires entitlement.",
        "Historical universe may contain survivorship bias.",
        "MFE/MAE are lower bounds excluding unknown exit-bar price ordering."]
