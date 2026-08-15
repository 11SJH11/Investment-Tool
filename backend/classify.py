"""
classify.py

Tags each ticker with its asset class (Stock / ETF / Commodity ETF / Crypto)
and, for individual stocks, its sector and industry. This lets the rest of
the tool group output meaningfully instead of one flat table, and lets the
diversification check explain *why* two things are correlated (e.g. "these
are both Energy sector" rather than just a bare number).
"""

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


# Keywords that suggest an ETF is commodity-focused, based on Yahoo's
# 'category' field (not perfectly reliable, but good enough as a heuristic)
COMMODITY_KEYWORDS = ["commodities", "commodity", "gold", "silver", "precious metals",
                       "energy limited partnership", "natural resources"]


def classify_ticker(ticker: str) -> dict:
    """Returns {ticker, quote_type, asset_class, sector, industry, category}"""
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    info = yf.Ticker(ticker).info
    quote_type = info.get("quoteType", "UNKNOWN")
    sector = info.get("sector")
    industry = info.get("industry")
    category = info.get("category")  # mainly populated for ETFs/mutual funds

    asset_class = _infer_asset_class(quote_type, category)

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "quote_type": quote_type,
        "asset_class": asset_class,
        "sector": sector or "N/A",
        "industry": industry or "N/A",
        "category": category or "N/A",
    }


def _infer_asset_class(quote_type: str, category: str) -> str:
    if quote_type == "CRYPTOCURRENCY":
        return "Crypto"
    if quote_type == "FUTURE":
        return "Futures"
    if quote_type == "EQUITY":
        return "Stock"
    if quote_type == "ETF":
        cat_lower = (category or "").lower()
        if any(kw in cat_lower for kw in COMMODITY_KEYWORDS):
            return "Commodity ETF"
        return "ETF (Other)"
    if quote_type == "MUTUALFUND":
        return "Mutual Fund"
    return quote_type or "Unknown"


def classify_multiple(tickers: list) -> pd.DataFrame:
    rows = [classify_ticker(t) for t in tickers]
    df = pd.DataFrame(rows).set_index("ticker")
    return df


def print_classification(df: pd.DataFrame):
    print("Ticker classification:")
    print(df[["name", "asset_class", "sector", "industry"]].to_string())


def grouped_tickers(df: pd.DataFrame, by: str = "asset_class") -> dict:
    """Returns {group_name: [tickers]} -- useful for printing grouped tables."""
    groups = {}
    for ticker, row in df.iterrows():
        key = row[by]
        groups.setdefault(key, []).append(ticker)
    return groups
