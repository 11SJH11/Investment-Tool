"""Shared existing calendar-front-v1 stitching, preserving raw dated prices."""
from datetime import datetime, time, timedelta, timezone
import pandas as pd
from app.core.safe_errors import MissingHistoryError


def calendar_front(contracts, root, start, end, load):
    start_date = start.date()
    end_date = end.date()
    eligible = [c for c in contracts if c.last_trade_date >= start_date and c.first_trade_date <= end_date]
    if not eligible:
        raise MissingHistoryError(f"No {root} contract overlaps {start_date} to {end_date}")

    # Calendar-front v1: the active front contract is the nearest dated
    # contract whose last-trade date has not passed. This is deterministic and
    # Uses UTC date boundaries, not exchange expiry instants. No volume/OI
    # crossover or TradingView equivalence is asserted.
    segments: list[pd.DataFrame] = []
    cursor = start
    for contract in eligible:
        if cursor >= end:
            break
        contract_end = datetime.combine(contract.last_trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        segment_start = max(cursor, start, datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc))
        segment_end = min(end, contract_end)
        if segment_start >= segment_end:
            continue
        frame = load(contract.ticker, segment_start, segment_end)
        if not frame.empty:
            prior = [c for c in contracts if c.last_trade_date < contract.last_trade_date]
            effective = max(datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc),
                datetime.combine(prior[-1].last_trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc)) if prior else datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc)
            frame["roll_method"] = "calendar-front"
            frame["roll_schedule_version"] = "calendar-front-v1"
            frame["contract_last_trade_date"] = contract.last_trade_date.isoformat()
            frame["roll_effective_at"] = effective.isoformat()
            segments.append(frame)
        cursor = max(cursor, contract_end)

    if not segments:
        return pd.DataFrame(columns=['timestamp','open','high','low','close','volume','source_contract'])
    output = pd.concat(segments, ignore_index=True)
    return (
        output.drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
