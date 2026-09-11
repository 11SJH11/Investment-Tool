from __future__ import annotations

import pandas as pd

from app.indicators.base import Indicator, IndicatorSpec
from app.indicators.registry import indicator_registry


def _series(bars: pd.DataFrame, column: str = "close") -> pd.Series:
    if column not in bars.columns:
        raise ValueError(f"Column '{column}' is not present in bars")
    return pd.to_numeric(bars[column], errors="coerce")


@indicator_registry.register
class Volume(Indicator):
    spec = IndicatorSpec(
        key="volume", name="Volume", overlay=False,
        defaults={}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        return _series(bars, "volume").rename("volume")


@indicator_registry.register
class SMA(Indicator):
    spec = IndicatorSpec(
        key="sma", name="Simple Moving Average", overlay=True,
        defaults={"length": 20, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        if length <= 0:
            raise ValueError("SMA length must be positive")
        source = str(params.get("source", self.spec.defaults["source"]))
        return _series(bars, source).rolling(length, min_periods=length).mean().rename("sma")


@indicator_registry.register
class EMA(Indicator):
    spec = IndicatorSpec(
        key="ema", name="Exponential Moving Average", overlay=True,
        defaults={"length": 20, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        if length <= 0:
            raise ValueError("EMA length must be positive")
        source = str(params.get("source", self.spec.defaults["source"]))
        return _series(bars, source).ewm(span=length, adjust=False, min_periods=length).mean().rename("ema")


@indicator_registry.register
class RSI(Indicator):
    spec = IndicatorSpec(
        key="rsi", name="Relative Strength Index", overlay=False,
        defaults={"length": 14, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        if length <= 0:
            raise ValueError("RSI length must be positive")
        source = str(params.get("source", self.spec.defaults["source"]))
        close = _series(bars, source)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        result = 100 - (100 / (1 + rs))
        result = result.where(avg_loss != 0, 100.0)
        return result.rename("rsi")


@indicator_registry.register
class ATR(Indicator):
    spec = IndicatorSpec(
        key="atr", name="Average True Range", overlay=False,
        defaults={"length": 14}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        if length <= 0:
            raise ValueError("ATR length must be positive")
        high = _series(bars, "high")
        low = _series(bars, "low")
        close = _series(bars, "close")
        previous_close = close.shift(1)
        tr = pd.concat(
            [(high - low).abs(), (high - previous_close).abs(), (low - previous_close).abs()],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean().rename("atr")


@indicator_registry.register
class VWAP(Indicator):
    spec = IndicatorSpec(
        key="vwap", name="Session VWAP", overlay=True,
        defaults={}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        if "timestamp" not in bars.columns:
            raise ValueError("VWAP requires timestamp data")
        volume = _series(bars, "volume").fillna(0)
        typical = (_series(bars, "high") + _series(bars, "low") + _series(bars, "close")) / 3.0
        timestamps = pd.to_datetime(bars["timestamp"], utc=True)
        # US-equity session date is based on New York, which is also what Ledger's
        # session filtering/backtester uses. This prevents VWAP resetting at UTC midnight.
        session_date = timestamps.dt.tz_convert("America/New_York").dt.date
        pv = typical * volume
        cumulative_pv = pv.groupby(session_date).cumsum()
        cumulative_volume = volume.groupby(session_date).cumsum().replace(0, float("nan"))
        return (cumulative_pv / cumulative_volume).rename("vwap")

@indicator_registry.register
class BollingerMiddle(Indicator):
    spec = IndicatorSpec(
        key="bb_middle", name="Bollinger Bands · middle", overlay=True,
        defaults={"length": 20, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        source = str(params.get("source", self.spec.defaults["source"]))
        if length <= 0:
            raise ValueError("Bollinger length must be positive")
        return _series(bars, source).rolling(length, min_periods=length).mean().rename("bb_middle")


@indicator_registry.register
class BollingerUpper(Indicator):
    spec = IndicatorSpec(
        key="bb_upper", name="Bollinger Bands · upper", overlay=True,
        defaults={"length": 20, "stddev": 2.0, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        mult = float(params.get("stddev", self.spec.defaults["stddev"]))
        source = str(params.get("source", self.spec.defaults["source"]))
        values = _series(bars, source)
        mid = values.rolling(length, min_periods=length).mean()
        std = values.rolling(length, min_periods=length).std(ddof=0)
        return (mid + std * mult).rename("bb_upper")


@indicator_registry.register
class BollingerLower(Indicator):
    spec = IndicatorSpec(
        key="bb_lower", name="Bollinger Bands · lower", overlay=True,
        defaults={"length": 20, "stddev": 2.0, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        mult = float(params.get("stddev", self.spec.defaults["stddev"]))
        source = str(params.get("source", self.spec.defaults["source"]))
        values = _series(bars, source)
        mid = values.rolling(length, min_periods=length).mean()
        std = values.rolling(length, min_periods=length).std(ddof=0)
        return (mid - std * mult).rename("bb_lower")


@indicator_registry.register
class MACD(Indicator):
    spec = IndicatorSpec(
        key="macd", name="MACD · line", overlay=False,
        defaults={"fast": 12, "slow": 26, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        fast = int(params.get("fast", self.spec.defaults["fast"]))
        slow = int(params.get("slow", self.spec.defaults["slow"]))
        if fast <= 0 or slow <= fast:
            raise ValueError("MACD requires slow > fast > 0")
        source = str(params.get("source", self.spec.defaults["source"]))
        values = _series(bars, source)
        fast_ema = values.ewm(span=fast, adjust=False, min_periods=fast).mean()
        slow_ema = values.ewm(span=slow, adjust=False, min_periods=slow).mean()
        return (fast_ema - slow_ema).rename("macd")


@indicator_registry.register
class MACDSignal(Indicator):
    spec = IndicatorSpec(
        key="macd_signal", name="MACD · signal", overlay=False,
        defaults={"fast": 12, "slow": 26, "signal": 9, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        fast = int(params.get("fast", self.spec.defaults["fast"]))
        slow = int(params.get("slow", self.spec.defaults["slow"]))
        signal = int(params.get("signal", self.spec.defaults["signal"]))
        source = str(params.get("source", self.spec.defaults["source"]))
        values = _series(bars, source)
        macd = values.ewm(span=fast, adjust=False, min_periods=fast).mean() - values.ewm(span=slow, adjust=False, min_periods=slow).mean()
        return macd.ewm(span=signal, adjust=False, min_periods=signal).mean().rename("macd_signal")


@indicator_registry.register
class MACDHistogram(Indicator):
    spec = IndicatorSpec(
        key="macd_histogram", name="MACD · histogram", overlay=False,
        defaults={"fast": 12, "slow": 26, "signal": 9, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        fast = int(params.get("fast", self.spec.defaults["fast"]))
        slow = int(params.get("slow", self.spec.defaults["slow"]))
        signal = int(params.get("signal", self.spec.defaults["signal"]))
        source = str(params.get("source", self.spec.defaults["source"]))
        values = _series(bars, source)
        macd = values.ewm(span=fast, adjust=False, min_periods=fast).mean() - values.ewm(span=slow, adjust=False, min_periods=slow).mean()
        signal_line = macd.ewm(span=signal, adjust=False, min_periods=signal).mean()
        return (macd - signal_line).rename("macd_histogram")


@indicator_registry.register
class RateOfChange(Indicator):
    spec = IndicatorSpec(
        key="roc", name="Rate of Change", overlay=False,
        defaults={"length": 12, "source": "close"}, causal=True,
    )

    def calculate(self, bars: pd.DataFrame, **params) -> pd.Series:
        length = int(params.get("length", self.spec.defaults["length"]))
        if length <= 0:
            raise ValueError("ROC length must be positive")
        source = str(params.get("source", self.spec.defaults["source"]))
        return (_series(bars, source).pct_change(length) * 100.0).rename("roc")
