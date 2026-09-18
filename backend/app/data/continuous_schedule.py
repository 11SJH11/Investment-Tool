"""Ledger's causal volume schedule; deliberately not a TradingView replica."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

VERSION = 'prior-session-volume45-v1'
NY = ZoneInfo('America/New_York')


def completion(row):
    """Conservative complete-session boundary, including shortened sessions."""
    stamp = pd.Timestamp(row['timestamp'])
    day = pd.Timestamp(row['session_end_date']).date()
    return max(stamp + pd.Timedelta(days=1), pd.Timestamp(datetime.combine(day, time(18), NY)))


def choose_roll(front, following, old, new):
    """Compare matching completed sessions; use only the *next* session's start.

    Selection is independent of intraday resolution and requested chart start.
    No next-session price/volume is consulted. Missing sessions are not zero.
    """
    fallback = pd.Timestamp(datetime.combine(front.last_trade_date + timedelta(days=1), time.min, timezone.utc))
    result = dict(effective_at=fallback.isoformat(), method='expiry-fallback',
                  from_contract=front.ticker, to_contract=following.ticker,
                  version=VERSION, evidence_at=None, close_gap=None)
    if old.empty or new.empty:
        return result
    required = {'timestamp','session_end_date','volume','close'}
    if not required.issubset(old.columns) or not required.issubset(new.columns):
        raise ValueError('Continuous roll selection requires provider session dates and volumes')
    old = old.sort_values('timestamp').drop_duplicates('session_end_date')
    new = new.sort_values('timestamp').drop_duplicates('session_end_date')
    merged = old.merge(new,on='session_end_date',suffixes=('_old','_new'))
    starts = sorted(pd.to_datetime(new.timestamp,utc=True))
    window = front.last_trade_date - timedelta(days=45)
    for row in merged.to_dict('records'):
        day = pd.Timestamp(row['session_end_date']).date()
        if not window <= day <= front.last_trade_date:
            continue
        values = [row['volume_old'],row['volume_new'],row['close_old'],row['close_new']]
        if not all(pd.notna(v) and float('-inf') < float(v) < float('inf') for v in values):
            raise ValueError('Invalid volume/close evidence for continuous roll')
        if row['volume_old'] < 0 or row['volume_new'] < 0:
            raise ValueError('Invalid negative futures volume')
        if row['volume_new'] <= row['volume_old']:
            continue
        available = max(completion(dict(timestamp=row['timestamp_old'],session_end_date=day)),
                        completion(dict(timestamp=row['timestamp_new'],session_end_date=day)))
        candidates = [s for s in starts if available <= s < fallback]
        if candidates:
            result.update(effective_at=candidates[0].isoformat(),method='prior-session-volume',
                          evidence_at=available.isoformat(),
                          close_gap=float(row['close_new'])-float(row['close_old']))
            break
    # Adjustment uses the latest common completed session before the actual roll.
    effective = pd.Timestamp(result['effective_at'])
    common = [r for r in merged.to_dict('records') if max(
        completion(dict(timestamp=r['timestamp_old'],session_end_date=r['session_end_date'])),
        completion(dict(timestamp=r['timestamp_new'],session_end_date=r['session_end_date']))) <= effective]
    if common:
        row = common[-1]
        result['close_gap'] = float(row['close_new'])-float(row['close_old'])
    return result


def adjust_continuous(frame, rolls):
    output = frame.copy()
    output['price_adjustment'] = 0.0
    if output.empty:
        return output
    for roll in rolls:
        effective = pd.Timestamp(roll['effective_at'])
        if effective <= output.timestamp.min() or effective > output.timestamp.max():
            continue
        gap = roll['close_gap']
        if gap is None or not float('-inf') < float(gap) < float('inf'):
            raise ValueError('Back-adjustment requires both contracts\' completed daily closes at the roll')
        output.loc[output.timestamp < effective,'price_adjustment'] += gap
    for col in ('open','high','low','close'):
        output[col] += output.price_adjustment
    output['adjustment_mode'] = 'back_adjusted'
    output['adjustment_method'] = 'backward-additive-prior-session-close-v1'
    return output
