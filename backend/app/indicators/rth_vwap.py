"""Causal cash-session traded-volume VWAP and population dispersion."""
from math import isfinite, sqrt

import pandas as pd

from app.indicators.base import Indicator, IndicatorSpec
from app.indicators.registry import indicator_registry


def session_moments(bars: pd.DataFrame) -> pd.DataFrame:
    rows = []
    day = None
    weight = mean = m2 = 0.0
    for bar in bars.itertuples(index=False):
        stamp = pd.Timestamp(bar.timestamp).tz_convert("America/New_York")
        if stamp.date() != day:
            day = stamp.date()
            weight = mean = m2 = 0.0
        if not 570 <= stamp.hour * 60 + stamp.minute < 960:
            rows.append((float("nan"), float("nan"), 0.0))
            continue
        volume = float(bar.volume)
        price = (float(bar.high) + float(bar.low) + float(bar.close)) / 3
        if not isfinite(volume) or volume < 0 or not isfinite(price):
            raise ValueError("VWAP requires finite prices and nonnegative traded volume")
        if volume:
            total = weight + volume
            delta = price - mean
            mean += volume / total * delta
            m2 += volume * delta * (price - mean)
            weight = total
        rows.append((mean if weight else float("nan"),
                     sqrt(max(0.0, m2 / weight)) if weight else float("nan"), weight))
    return pd.DataFrame(rows, index=bars.index, columns=["vwap", "sd", "weight"])


@indicator_registry.register
class RthVwapBands(Indicator):
    spec = IndicatorSpec(key="rth_vwap_bands", name="RTH VWAP / population bands",
                         defaults={"line": "vwap", "deviations": 2.0}, causal=True)

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        line = params.get("line", "vwap")
        deviations = float(params.get("deviations", 2.0))
        if line not in {"vwap", "upper", "lower", "sd"} or not isfinite(deviations) or deviations <= 0:
            raise ValueError("Choose vwap/upper/lower/sd and a positive deviation multiplier")
        values = session_moments(bars)
        if line in {"vwap", "sd"}:
            return values[line]
        return values.vwap + (1 if line == "upper" else -1) * deviations * values.sd
