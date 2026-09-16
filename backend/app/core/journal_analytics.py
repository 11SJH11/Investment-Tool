"""One date/filter/aggregation contract for Journal, Calendar and Daily Review."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
    output = []
    for trade in trades:
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
    return {
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
