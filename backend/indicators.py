"""
indicators.py

A plugin-style registry for technical indicators. To add a new indicator,
write a function, decorate it with @indicator(...), and it automatically
becomes available via list_indicators() and compute_indicator() -- no
changes needed anywhere else (not in main.py, not in the frontend, which
reads the available list dynamically from /api/indicators).

Honest framing, worth keeping in mind while using these: technical
indicators describe past price action. They are not proven predictors of
future price action -- academic evidence on their predictive power is
mixed at best. Useful for pattern recognition and context, not signals to
blindly trust.

All indicator functions take a pandas DataFrame with at least a 'Close'
column (also 'Open'/'High'/'Low'/'Volume' where relevant) and return either
a single pandas Series (for single-line indicators like SMA) or a dict of
named Series (for multi-line indicators like MACD or Bollinger Bands).
"""

import pandas as pd

INDICATOR_REGISTRY = {}


def indicator(key: str, label: str, params: dict = None, output: str = "single"):
    """
    Decorator to register an indicator.
    key: unique identifier, e.g. "sma"
    label: human-readable name, e.g. "Simple Moving Average"
    params: default parameter values, e.g. {"window": 20}
    output: "single" (one line, overlays on price) or "multi" (several
            named lines) or "separate" (own chart pane, e.g. RSI/MACD)
    """
    def decorator(func):
        INDICATOR_REGISTRY[key] = {"func": func, "label": label, "params": params or {}, "output": output}
        return func
    return decorator


def list_indicators() -> list:
    return [
        {"key": k, "label": v["label"], "params": v["params"], "output": v["output"]}
        for k, v in INDICATOR_REGISTRY.items()
    ]


def compute_indicator(key: str, price_df: pd.DataFrame, **params) -> dict:
    """
    Returns {"key": ..., "output": "single"|"multi"|"separate", "series": {...}}
    where series is always a dict of {line_name: {date_str: value}} so it's
    trivially JSON-serializable regardless of single- or multi-line output.
    """
    if key not in INDICATOR_REGISTRY:
        raise ValueError(f"Unknown indicator: {key}")
    spec = INDICATOR_REGISTRY[key]
    merged_params = {**spec["params"], **params}
    result = spec["func"](price_df, **merged_params)

    if isinstance(result, pd.Series):
        series = {key: _series_to_dict(result)}
    elif isinstance(result, dict):
        series = {name: _series_to_dict(s) for name, s in result.items()}
    else:
        raise TypeError(f"Indicator '{key}' returned unsupported type: {type(result)}")

    return {"key": key, "label": spec["label"], "output": spec["output"], "series": series}


def _series_to_dict(s: pd.Series) -> dict:
    return {str(idx.date() if hasattr(idx, "date") else idx): (None if pd.isna(v) else round(float(v), 4))
            for idx, v in s.items()}


# ---------------------------------------------------------------------------
# Built-in indicators. Each is a self-contained example of how to add a new
# one -- copy the pattern below for anything else you want.
# ---------------------------------------------------------------------------

@indicator("sma", "Simple Moving Average", params={"window": 20}, output="single")
def sma(df: pd.DataFrame, window: int = 20) -> pd.Series:
    return df["Close"].rolling(window).mean()


@indicator("ema", "Exponential Moving Average", params={"window": 20}, output="single")
def ema(df: pd.DataFrame, window: int = 20) -> pd.Series:
    return df["Close"].ewm(span=window, adjust=False).mean()


@indicator("rsi", "Relative Strength Index", params={"window": 14}, output="separate")
def rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


@indicator("macd", "MACD", params={"fast": 12, "slow": 26, "signal": 9}, output="separate")
def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


@indicator("bollinger", "Bollinger Bands", params={"window": 20, "num_std": 2}, output="multi")
def bollinger(df: pd.DataFrame, window: int = 20, num_std: float = 2) -> dict:
    mid = df["Close"].rolling(window).mean()
    std = df["Close"].rolling(window).std()
    return {"upper": mid + num_std * std, "middle": mid, "lower": mid - num_std * std}


@indicator("vwap", "Volume Weighted Average Price", params={}, output="single")
def vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    return (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()
