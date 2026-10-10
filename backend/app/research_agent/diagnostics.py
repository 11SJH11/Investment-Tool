"""Saved-evidence diagnostics. No market reads, strategy calls or inferred causality."""
from collections import defaultdict
from datetime import datetime
from math import isfinite
from statistics import mean
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")
LARGE_WINNER_R = 2.0  # Descriptive threshold, fixed before inspecting results.


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) else None


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(ZONE) if result.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def outcome(trade):
    pnl = number(trade.get("net_pnl"))
    return "unknown" if pnl is None else "winner" if pnl > 0 else "loser" if pnl < 0 else "breakeven"


def large_winner(trade):
    r = number(trade.get("r_multiple"))
    return outcome(trade) == "winner" and r is not None and r >= LARGE_WINNER_R


def excursions(trades):
    result = {}
    for metric in ("mfe", "mae"):
        values = []
        lower_bound_n = 0
        for trade in trades:
            meta = trade.get("metadata") or {}
            value = number(meta.get(metric + "_r"))
            if value is None:
                value = number(meta.get(metric + "_r_lower_bound"))
                lower_bound_n += value is not None
            if value is not None:
                values.append(value)
        result.update({metric + "_n": len(values), "average_" + metric + "_r": mean(values) if values else None,
                       metric + "_lower_bound_n": lower_bound_n})
    return result


def diagnostics(trades, summarize):
    dimensions = {k: defaultdict(list) for k in ("year", "month", "weekday", "entry_hour", "direction", "exit_reason", "outcome", "trade_number")}
    days = defaultdict(list)
    for index, trade in enumerate(trades):
        when = timestamp(trade.get("entry_time"))
        for dimension, value in {
            "year": when.strftime("%Y") if when else "unknown",
            "month": when.strftime("%Y-%m") if when else "unknown",
            "weekday": when.strftime("%a") if when else "unknown",
            "entry_hour": when.strftime("%H") if when else "unknown",
            "direction": trade.get("direction") or "unknown",
            "exit_reason": trade.get("exit_reason") or "unknown",
            "outcome": outcome(trade),
        }.items():
            dimensions[dimension][value].append(trade)
        if not when:
            dimensions["trade_number"]["unknown"].append(trade)
        if when:
            days[(trade.get("symbol", "unknown"), when.date().isoformat())].append((when, index, trade))
    sequences = []
    for (symbol, day), rows in sorted(days.items()):
        rows.sort(key=lambda item: (item[0], item[1]))
        ambiguous = len({row[0] for row in rows}) != len(rows)
        items = []
        for ordinal, (_, _, trade) in enumerate(rows, 1):
            slot = "ambiguous" if ambiguous else str(ordinal)
            dimensions["trade_number"][slot].append(trade)
            items.append({k: trade.get(k) for k in ("direction", "entry_time", "exit_time", "r_multiple", "net_pnl", "exit_reason")})
        sequences.append({"symbol": symbol, "date": day, "ambiguous_order": ambiguous, "trades": items})
    positive = [number(t.get("net_pnl")) for t in trades if outcome(t) == "winner"]
    denominator = sum(positive)
    monthly = [sum(number(t.get("net_pnl")) or 0 for t in rows if outcome(t) == "winner") for rows in dimensions["month"].values()]
    stress = []
    complete = bool(trades) and all(number(t.get("net_pnl")) is not None and number(t.get("fees")) is not None and t["fees"] >= 0 for t in trades)
    if complete:
        for multiplier in (0, .25, .5, 1):
            stress.append({"additional_recorded_fee_fraction": multiplier,
                           "net_pnl": sum(t["net_pnl"] - multiplier * t["fees"] for t in trades)})
    return {
        "breakdowns": {d: {k: summarize(rows) for k, rows in sorted(groups.items())} for d, groups in dimensions.items()},
        "daily_sequences": sequences,
        "day_basis": "New York calendar entry date, per symbol; not an exchange-session ID. Trade ordinal counts executed trades, not rejected setups.",
        "large_winners": summarize([t for t in trades if large_winner(t)]),
        "large_winner_threshold_r": LARGE_WINNER_R,
        "session_close_winners": summarize([t for t in trades if outcome(t) == "winner" and t.get("exit_reason") == "session_close"]),
        "concentration": {"basis": "Share of observed positive net P&L, not net total; unknown P&L excluded.",
                          "pnl_n": sum(number(t.get("net_pnl")) is not None for t in trades),
                          "top_trade_positive_pnl_share": max(positive) / denominator if denominator else None,
                          "top_month_positive_pnl_share": max(monthly) / denominator if denominator else None},
        "fee_stress": {"rows": stress, "available": complete,
                       "limitation": "Arithmetic sensitivity to additional recorded fees, fixed fills/size/path. Not a rerun, slippage estimate, or capital-constrained simulation."},
    }
