"""Display-only equity projection. Stored observations/metrics are never changed."""
import math


def display_curve(points, buckets=256):
    if len(points)<=4096:
        return list(points)
    selected={0,len(points)-1}
    width=math.ceil(len(points)/buckets)
    fields=('equity','return_pct','drawdown_pct','cumulative_r')
    for begin in range(0,len(points),width):
        end=min(len(points),begin+width)
        selected.update((begin,end-1))
        for key in fields:
            valid=[i for i in range(begin,end) if isinstance(points[i].get(key),(int,float))
                   and math.isfinite(points[i][key])]
            if valid:
                selected.add(min(valid,key=lambda i:points[i][key]))
                selected.add(max(valid,key=lambda i:points[i][key]))
        for i in range(begin,end):
            if points[i].get('closed_trades') or points[i].get('realized_pnl'):
                selected.add(i)
            # Preserve missing-value boundaries instead of drawing through gaps.
            if i and any((points[i].get(k) is None)!=(points[i-1].get(k) is None) for k in fields):
                selected.update((i-1,i))
    return [points[i] for i in sorted(selected)]
