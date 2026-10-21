"""Interpret receipt-time samples as observations, never a trading clock policy."""
import math
from statistics import median


def summarize(samples):
    result = dict(status='unverified', observed_offset_seconds=None,
                  dst_rule_verified=False, execution_enabled=False,
                  limitation='Receipt-clock evidence only; host UTC accuracy, historical bar convention and seasonal transitions require independent verification.')
    if len(samples) < 3:
        return result
    values = []
    for sample in samples:
        receipt, tick = sample.get('receipt_ms'), sample.get('tick_ms')
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (receipt, tick)):
            return result
        values.append((receipt, tick))
    if any(b[0] <= a[0] or b[1] < a[1] for a,b in zip(values, values[1:])):
        return result
    if len({v[1] for v in values}) < 3:
        return {**result, 'status': 'insufficient_advancing_ticks'}
    receipt_span = values[-1][0]-values[0][0]
    tick_span = values[-1][1]-values[0][1]
    if not .25 <= tick_span/receipt_span <= 4:
        return result
    offsets = [(tick-receipt)/1000 for receipt,tick in values]
    candidates = [offset for offset in (0,7200,10800)
                  if all(abs(v-offset) <= 5 for v in offsets)]
    if len(candidates) != 1:
        return result
    return {**result, 'status': 'current_offset_observed',
            'observed_offset_seconds': candidates[0],
            'median_residual_seconds': median(offsets)-candidates[0],
            'sample_count': len(samples)}
