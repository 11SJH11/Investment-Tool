"""Small causal quote/activity concepts in the existing canonical registry."""
from collections import deque
import math
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .base import Observation
from .registry import Definition, registry


class NoTickParams(BaseModel):
    model_config = ConfigDict(extra='forbid')


class WindowParams(NoTickParams):
    seconds: int = Field(default=60, ge=1, le=3600, strict=True)


def quote_spread(row):
    bid, ask = getattr(row, 'bid', None), getattr(row, 'ask', None)
    if not all(isinstance(v, (float, int)) and math.isfinite(v) and v > 0 for v in (bid, ask)):
        return None
    return float(ask-bid) if ask >= bid else None


def current_spread(frame, params, dependencies):
    return [Observation(kind='series', label='Observed quote spread (price)',
        occurred_at=row.timestamp, confirmed_at=row.timestamp, available_at=row.available_at,
        value=quote_spread(row)) for row in frame.itertuples()]


def windows(frame, params, count=False):
    if frame.empty:
        return []
    window, output, total, missing = deque(), [], 0.0, 0
    first = frame.timestamp.iloc[0]
    for row in frame.itertuples():
        spread = quote_spread(row)
        boundary = row.timestamp - pd.Timedelta(seconds=params['seconds'])
        window.append((row.timestamp, spread))
        total += spread or 0
        missing += spread is None
        while window and window[0][0] <= boundary:
            _, removed = window.popleft()
            total -= removed or 0
            missing -= removed is None
        # Missing warmup never becomes a partially populated "full" window.
        value = None
        if first <= boundary:
            value = float(len(window)) if count else total / len(window) if not missing else None
        output.append(Observation(kind='series', label='Observed tick count' if count else 'Quote-weighted mean spread',
            occurred_at=row.timestamp, confirmed_at=row.timestamp, available_at=row.available_at, value=value))
    return output


def mean_spread(frame, params, dependencies):
    return windows(frame, params)


def tick_count(frame, params, dependencies):
    return windows(frame, params, count=True)


LIMITATIONS = ('Observed broker quote events only; not exchange trade volume, DOM or proof of complete feed coverage. '
              'Historical event time is not measured delivery latency. Preserve supplied available_at. '
              'No forward filling or execution/fill assumption.')
registry.register(Definition('spread.current.v1', 'Current ask minus bid in price units; missing/crossed quotes yield null.',
    current_spread, NoTickParams, input_kind='ticks', limitations=LIMITATIONS))
registry.register(Definition('spread.mean_window.v1', 'Arithmetic quote-weighted mean spread over (t-window,t], requiring full warmup and valid quotes.',
    mean_spread, WindowParams, input_kind='ticks', limitations=LIMITATIONS))
registry.register(Definition('tick_activity.count.v1', 'Count observed events over (t-window,t], including equal-timestamp events in provider order; full warmup required.',
    tick_count, WindowParams, input_kind='ticks', limitations=LIMITATIONS))
