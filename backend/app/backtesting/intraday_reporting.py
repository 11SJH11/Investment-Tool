from app.performance import timed, profiled, measure
"""Post-simulation diagnostics; never an input to strategy eligibility."""
import pandas as pd
from .excursion_reporting import excursion_diagnostics


@timed('excursion_reporting')
def annotate_intraday(result, frames):
    outcomes = {}
    for trade in result["trades"]:
        bars = frames.get(trade["symbol"], {}).get("1m")
        stamps = pd.to_datetime(bars.timestamp, utc=True) if bars is not None else pd.Series([], dtype="datetime64[ns, UTC]")
        start, end = pd.Timestamp(trade["entry_time"]), pd.Timestamp(trade["exit_time"])
        held = (stamps >= start) & (stamps < end)
        outcome = dict(entry=trade["entry_price"], stop=trade["stop_loss"], target=trade["take_profit"],
            exit=trade["exit_price"], result_r=trade["r_multiple"], exit_reason=trade["exit_reason"],
            excursion_measurement="lower_bound_excluding_exit_bar", bars_in_trade=int(held.sum()),
            minutes_in_trade=(end-start).total_seconds()/60)
        setup = next((s for s in result.get("setups", []) if s.get("symbol") == trade["symbol"] and s.get("entry_time") == trade["entry_time"]), None)
        outcome.update(excursion_diagnostics(trade, bars, entry_at_open=bool(setup and setup.get("order_type") == "market")))
        outcome["excursion_timing"] = "completed_1m_bar_bound_or_exact_fill"
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
