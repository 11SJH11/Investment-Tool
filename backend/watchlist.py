"""
watchlist.py

A simple persistent list of tickers you're keeping an eye on -- separate
from your actual holdings (Portfolio). Starts with a small sensible preset,
but you can add or remove anything. Fetching live data for the list is a
separate, explicit step (not automatic on every page load) since it means
a live network call per ticker.
"""

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "watchlist_state.json")

DEFAULT_WATCHLIST = ["AAPL", "MSFT", "VOO", "GLD"]


def load_watchlist() -> list:
    if not os.path.exists(STATE_FILE):
        return list(DEFAULT_WATCHLIST)
    with open(STATE_FILE) as f:
        data = json.load(f)
    return data.get("tickers", list(DEFAULT_WATCHLIST))


def save_watchlist(tickers: list):
    with open(STATE_FILE, "w") as f:
        json.dump({"tickers": tickers}, f, indent=2)


def add_ticker(ticker: str) -> list:
    tickers = load_watchlist()
    ticker = ticker.upper().strip()
    if ticker and ticker not in tickers:
        tickers.append(ticker)
        save_watchlist(tickers)
    return tickers


def remove_ticker(ticker: str) -> list:
    tickers = load_watchlist()
    ticker = ticker.upper().strip()
    tickers = [t for t in tickers if t != ticker]
    save_watchlist(tickers)
    return tickers


def fetch_watchlist_data(tickers: list) -> list:
    """
    Live snapshot for each watchlist ticker: current price, day change %,
    and a couple of headline fundamentals. One yfinance call per ticker --
    fine for a watchlist-sized list (a handful to a few dozen), not meant
    for scanning hundreds (use market_scanner for that).
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    results = []
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("previousClose")
            change_pct = ((price - prev_close) / prev_close * 100) if price and prev_close else None
            results.append({
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "price": price,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "beta": info.get("beta"),
                "error": None,
            })
        except Exception as e:
            results.append({"ticker": ticker, "name": ticker, "price": None, "change_pct": None,
                             "market_cap": None, "pe_ratio": None, "beta": None, "error": str(e)})
    return results
