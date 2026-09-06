import pandas as pd

from app.indicators import indicator_registry


def bars():
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-02 14:30", periods=30, freq="5min", tz="UTC"),
        "open": range(100, 130),
        "high": [x + 1 for x in range(100, 130)],
        "low": [x - 1 for x in range(100, 130)],
        "close": [x + 0.5 for x in range(100, 130)],
        "volume": [1000] * 30,
    })


def test_builtin_indicators_are_registered():
    keys = {spec.key for spec in indicator_registry.specs()}
    assert {"sma", "ema", "rsi", "atr", "vwap", "bb_upper", "bb_middle", "bb_lower", "macd", "macd_signal", "macd_histogram", "roc"}.issubset(keys)


def test_indicators_produce_point_in_time_series():
    frame = bars()
    ema = indicator_registry.create("ema").calculate(frame, length=5)
    atr = indicator_registry.create("atr").calculate(frame, length=5)
    vwap = indicator_registry.create("vwap").calculate(frame)
    assert len(ema) == len(frame)
    assert ema.iloc[-1] > ema.iloc[-2]
    assert atr.iloc[-1] > 0
    assert vwap.notna().any()
