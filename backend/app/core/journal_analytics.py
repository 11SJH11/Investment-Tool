"""One date/filter/aggregation contract for Journal, Calendar and Daily Review."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import math


DIMENSIONS = ("ticker", "account", "external_provider", "environment", "source", "playbook_id",
              "setup", "setup_grade", "plan_followed", "direction", "session_time", "market_condition",
              "structure_alignment", "entry_relativity", "shift", "confluences", "mistakes", "emotions",
              "weekday", "entry_hour", "month", "result")


def dimension_values(trade, key, zone):
    local = trade_date(trade, zone)
    formats = {"weekday": "%A", "entry_hour": "%H:00", "month": "%Y-%m"}
    if key in formats:
        value = local.strftime(formats[key]) if local else None
    elif key == "environment":
        value = trade.get("source_metadata", {}).get("environment")
    elif key in ("structure_alignment", "entry_relativity", "shift", "confluences", "mistakes", "emotions"):
        value = trade.get("review_data", {}).get(key)
    else:
        value = trade.get(key)
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(str(v) if v is not None and v != "" else "Unlabelled" for v in (values or [None])))


def parse_dimensions(filters):
    try:
        values = json.loads(filters.get("dimensions_json") or "{}")
    except (ValueError, TypeError):
        raise ValueError("Journal dimensions must be a JSON object of selected value arrays") from None
    if not isinstance(values, dict) or any(k not in DIMENSIONS or not isinstance(v, list)
            or any(not isinstance(x, str) for x in v) for k, v in values.items()):
        raise ValueError("Journal dimensions must contain supported fields and string arrays")
    return values


def filter_options(rows, timezone_name):
    zone = journal_zone(timezone_name)
    return {key: sorted({v for t in rows for v in dimension_values(t, key, zone)}) for key in DIMENSIONS}


def journal_zone(value):
    try:
        return ZoneInfo(value or "UTC")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("Choose a valid IANA journal timezone") from None


def timestamp(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def trade_date(trade, zone):
    # Entry date is the journal day, regardless of when the trade was closed.
    value = timestamp(trade.get("opened_at"))
    return value.astimezone(zone) if value else None


def filter_trades(trades, filters):
    zone = journal_zone(filters.get("timezone"))
    dimensions = parse_dimensions(filters)
    output = []
    for trade in trades:
        if any(selected and not set(selected).intersection(dimension_values(trade, key, zone))
               for key, selected in dimensions.items()):
            continue
        if any(str(trade.get(key) or "") != str(filters[key]) for key in
               ("source", "account", "external_account_key", "playbook_id", "direction", "result", "setup_grade", "plan_followed", "entry_timeframe", "session_time") if filters.get(key)):
            continue
        if any(str(filters[key]).casefold() not in str(trade.get(key) or "").casefold()
               for key in ("ticker", "setup", "market_condition") if filters.get(key)):
            continue
        day = trade_date(trade, zone)
        day = day.date().isoformat() if day else ""
        if filters.get("date_from") and day < filters["date_from"]:
            continue
        if filters.get("date_to") and (not day or day > filters["date_to"]):
            continue
        output.append({**trade, "journal_date": day or None})
    return output


def summary(rows):
    closed = [t for t in rows if t.get("status") == "closed"]
    results = Counter(t.get("result") for t in closed)
    rs = [float(t["r_multiple"]) for t in closed if t.get("r_multiple") is not None]
    wins, losses, breakevens = (results[k] for k in ("win", "loss", "breakeven"))
    money = defaultdict(float)
    money_counts = Counter()
    for t in closed:
        if t.get("pnl_amount") is not None:
            currency = t.get("account_currency") or t.get("position_currency") or "USD"
            money[currency] += float(t["pnl_amount"])
            money_counts[currency] += 1
    positive, negative = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    curve = peak = drawdown = 0.0
    streak = longest = 0
    for t in sorted(closed, key=lambda x: (timestamp(x.get("closed_at")) or timestamp(x.get("opened_at")) or datetime.min.replace(tzinfo=timezone.utc), x["id"])):
        if t.get("r_multiple") is not None:
            curve += float(t["r_multiple"]); peak = max(peak, curve); drawdown = min(drawdown, curve - peak)
        if t.get("result") == "loss":
            streak += 1; longest = max(longest, streak)
        elif t.get("result") in {"win", "breakeven"}:
            streak = 0
    durations = []
    for t in closed:
        start, end = timestamp(t.get("opened_at")), timestamp(t.get("closed_at"))
        if start and end and end >= start:
            durations.append((end - start).total_seconds() / 60)
    planned = [float(t["planned_rr"]) for t in rows if t.get("planned_rr") is not None]
    percentages = [float(t["pnl_pct"]) for t in closed if t.get("pnl_pct") is not None]
    winner_rs, loser_rs = [r for r in rs if r > 0], [r for r in rs if r < 0]
    plans = [str(t.get("plan_followed") or "").lower() for t in rows
             if str(t.get("plan_followed") or "").lower() in {"yes", "no", "partially"}]
    excursions = {}
    for name in ("mfe", "mae"):
        values = []
        for t in closed:
            meta = t.get("source_metadata") or {}
            try:
                value = meta.get(f"{name}_r")
                if value is None and meta.get(f"{name}_per_share") is not None and t.get("entry_price") is not None and t.get("stop_loss") is not None:
                    risk = abs(float(t["entry_price"]) - float(t["stop_loss"]))
                    if risk:
                        value = float(meta[f"{name}_per_share"])/risk
                if value is not None and math.isfinite(float(value)):
                    values.append(float(value))
            except (TypeError, ValueError):
                pass
        excursions[f"average_{name}_r"] = sum(values)/len(values) if values else None
        excursions[f"{name}_trades"] = len(values)
    return {
        **excursions,
        "average_winner_r": sum(winner_rs)/len(winner_rs) if winner_rs else None,
        "average_loser_r": sum(loser_rs)/len(loser_rs) if loser_rs else None,
        "winner_r_trades": len(winner_rs), "loser_r_trades": len(loser_rs),
        "plan_followed_pct": 100*plans.count("yes")/len(plans) if plans else None, "plan_trades": len(plans),
        "grade_distribution": dict(Counter(t.get("setup_grade") or "Unlabelled" for t in rows)),
        "duration_trades": len(durations),
        "trades": len(rows), "closed_trades": len(closed), "wins": wins, "losses": losses, "breakevens": breakevens,
        "decided_trades": wins + losses, "win_rate": wins / (wins + losses) * 100 if wins + losses else None,
        "r_trades": len(rs), "average_r": sum(rs) / len(rs) if rs else None, "avg_r": sum(rs) / len(rs) if rs else None,
        "total_r": sum(rs) if rs else None, "profit_factor_r": positive / negative if negative else ("inf" if positive else None),
        "pnl_by_currency": [{"currency": c, "total_pnl": money[c], "trades": money_counts[c]} for c in sorted(money)],
        "total_pnl": next(iter(money.values())) if len(money) == 1 else None,
        "pnl_trades": sum(money_counts.values()), "unknown_outcomes": len(closed) - wins - losses - breakevens,
        "avg_pnl_pct": sum(percentages) / len(percentages) if percentages else None, "avg_planned_rr": sum(planned) / len(planned) if planned else None,
        "average_duration_min": sum(durations) / len(durations) if durations else None,
        "max_drawdown_r": drawdown if rs else None, "longest_losing_streak": longest,
    }


def report(rows, filters):
    zone = journal_zone(filters.get("timezone"))
    def local(t, fmt):
        dt = trade_date(t, zone)
        return dt.strftime(fmt) if dt else "Unknown"
    extractors = {
        "symbol": lambda t: t.get("ticker"), "setup": lambda t: t.get("setup"),
        "playbook": lambda t: t.get("playbook_title") or "Unlinked", "setup_grade": lambda t: t.get("setup_grade"),
        "plan_followed": lambda t: t.get("plan_followed"), "direction": lambda t: t.get("direction"),
        "timeframe": lambda t: t.get("entry_timeframe"), "market_condition": lambda t: t.get("market_condition"),
        "structure_alignment": lambda t: t.get("review_data", {}).get("structure_alignment"),
        "session": lambda t: t.get("session_time"), "weekday": lambda t: local(t, "%A"),
        "entry_hour": lambda t: local(t, "%H:00"), "source": lambda t: t.get("source"),
        "provider": lambda t: t.get("external_provider"), "account": lambda t: t.get("account"),
        "mistake": lambda t: t.get("review_data", {}).get("mistakes", []),
        "emotion": lambda t: t.get("review_data", {}).get("emotions", []),
    }
    # Custom buckets are scoped by Playbook and stable field ID; renamed labels do not erase answers.
    for t in rows:
        for key in t.get("review_data", {}).get("custom", {}):
            group = f"playbook_field:{key}"
            extractors[group] = lambda t, key=key: t.get("review_data", {}).get("custom", {}).get(key)
    groups = {}
    for name, getter in extractors.items():
        buckets = defaultdict(list)
        for t in rows:
            value = getter(t)
            values = value if isinstance(value, list) else [value]
            for v in dict.fromkeys(str(v or "Unlabelled") for v in (values or [None])):
                buckets[v].append(t)
        groups[name] = sorted(({name: k, **summary(v)} for k, v in buckets.items()), key=lambda x: x["trades"], reverse=True)
    return {"filters": filters, "timezone": str(zone), "date_basis": "entry", "summary": summary(rows), "breakdowns": groups, "trades": rows}


def daily_summary(rows):
    result = summary(rows)
    result["instruments"] = sorted({t["ticker"] for t in rows})
    for field, name in (("session_time", "sessions"), ("setup", "setups"), ("playbook_title", "playbooks"), ("setup_grade", "grades"), ("plan_followed", "plan_adherence")):
        result[name] = dict(Counter(t.get(field) or "Unlabelled" for t in rows))
    result["mistakes"] = dict(Counter(tag for t in rows for tag in t.get("review_data", {}).get("mistakes", [])))
    return result
