"""Declared development regimes; never infer labels from backtest performance."""
from pydantic import Field
from .robustness import Window


class DeclaredRegime(Window):
    name: str = Field(min_length=1, max_length=80)
    definition: str = Field(min_length=1, max_length=2000)
    evidence_source: str = Field(min_length=1, max_length=1000)


def validate_windows(windows, start=None, end=None):
    names = [w['name'].casefold() for w in windows]
    if len(names) != len(set(names)):
        raise ValueError('Regime names must be unique')
    if any(a['end'] >= b['start'] for a, b in zip(windows, windows[1:])):
        raise ValueError('Declared regimes must be chronological and disjoint')
    if start is not None and any(not start <= w['start'] <= w['end'] <= end for w in windows):
        raise ValueError('Declared regimes must remain inside the frozen development range')
    return windows
