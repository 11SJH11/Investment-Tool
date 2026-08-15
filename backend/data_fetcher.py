"""
data_fetcher.py

Pulls historical price data for stocks, ETFs, and crypto tickers via yfinance,
with local CSV caching so you're not hammering the API on every run.

Crypto tickers on Yahoo Finance use the format "BTC-USD", "ETH-USD", etc.
"""

import os
from datetime import datetime, timedelta
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(ticker: str) -> str:
    safe = ticker.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}.csv")


def _strip_timezone(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """
    yfinance returns timestamps localized to the exchange's timezone
    (e.g. America/New_York). Comparing that directly against a plain
    (timezone-naive) pd.Timestamp raises a TypeError -- this was the root
    cause of "price not found" errors on every date, not just specific ones.
    Strip tz info so downstream comparisons work regardless of ticker/date.
    """
    if index.tz is not None:
        return index.tz_localize(None)
    return index


def fetch_price_history(ticker: str, start: str = "2015-01-01", end: str = None,
                         force_refresh: bool = False) -> pd.DataFrame:
    """
    Returns a DataFrame indexed by date with a 'Close' column (adjusted close)
    for the given ticker. Uses a local cache to avoid refetching every call.
    """
    end = end or datetime.today().strftime("%Y-%m-%d")
    path = _cache_path(ticker)

    if not force_refresh and os.path.exists(path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if df.index.min() <= pd.Timestamp(start) and df.index.max() >= pd.Timestamp(end) - pd.Timedelta(days=5):
            return df.loc[start:end]

    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'. Check the symbol.")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = _strip_timezone(raw.index)

    df = raw[["Close"]].copy()
    df.index.name = "Date"
    df.to_csv(path)
    return df.loc[start:end]


def fetch_multiple(tickers: list, start: str = "2015-01-01", end: str = None) -> pd.DataFrame:
    """Returns a DataFrame with one 'Close' column per ticker, aligned by date."""
    frames = {}
    for t in tickers:
        df = fetch_price_history(t, start=start, end=end)
        frames[t] = df["Close"]
    combined = pd.DataFrame(frames)
    combined = combined.dropna(how="all")
    return combined


def fetch_ohlcv(ticker: str, start: str = "2015-01-01", end: str = None) -> pd.DataFrame:
    """
    Returns full OHLCV data (Open, High, Low, Close, Volume) for one ticker --
    needed for candlestick charts and volume-based indicators like VWAP.
    Not cached (used less frequently than plain Close history).
    """
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")
    end = end or datetime.today().strftime("%Y-%m-%d")
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No data returned for ticker '{ticker}'. Check the symbol.")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = _strip_timezone(raw.index)
    raw.index.name = "Date"
    return raw


def get_price_on_date(ticker: str, date_str: str) -> dict:
    """
    Returns the closing price for a ticker on (or nearest trading day before)
    the given date -- used to auto-fill "price paid" when logging a
    contribution by date instead of typing the price manually.

    date_str: "YYYY-MM-DD"
    Returns {"date_requested": ..., "date_used": ..., "price": ..., "exact_match": bool}
    """
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    requested = pd.Timestamp(date_str)
    window_start = (requested - timedelta(days=21)).strftime("%Y-%m-%d")
    window_end = (requested + timedelta(days=1)).strftime("%Y-%m-%d")

    t = yf.Ticker(ticker)
    raw = t.history(start=window_start, end=window_end, auto_adjust=True)

    if raw.empty:
        raise ValueError(
            f"Yahoo Finance returned no data at all for '{ticker}' in the window "
            f"{window_start} to {window_end}. Check the ticker symbol is correct."
        )

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = _strip_timezone(raw.index)

    valid = raw[raw.index <= requested]
    if valid.empty:
        earliest = raw.index.min().date()
        raise ValueError(
            f"'{ticker}' has price data starting {earliest}, but nothing at or before "
            f"{date_str} within the lookback window. If {date_str} is before the "
            f"company's IPO or before Yahoo's coverage starts, that's expected."
        )

    row = valid.iloc[-1]
    date_used = valid.index[-1]

    return {
        "date_requested": date_str,
        "date_used": str(date_used.date()),
        "price": round(float(row["Close"]), 4),
        "exact_match": str(date_used.date()) == date_str,
    }


def get_current_price(ticker: str) -> float:
    """Returns the latest available closing price for a ticker."""
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")
    t = yf.Ticker(ticker)
    info = t.info
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price is None:
        hist = t.history(period="5d")
        if hist.empty:
            raise ValueError(f"Could not determine current price for '{ticker}'.")
        price = float(hist["Close"].iloc[-1])
    return round(float(price), 4)
