"""
sector_valuation.py

Compares a stock's valuation to its OWN sector's typical valuation, instead
of comparing e.g. a tech stock's P/E to an energy stock's P/E (which tells
you very little -- different sectors trade at structurally different
multiples for legitimate reasons).

Uses sector ETFs as the comparison baseline -- a reasonable, transparent
proxy for "what does the market typically pay for this sector."
"""

try:
    import yfinance as yf
except ImportError:
    yf = None

# Sector -> representative sector ETF ticker
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Financial": "XLF",
    "Consumer Defensive": "XLP",
    "Consumer Cyclical": "XLY",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Communication Services": "XLC",
}


def get_sector_pe(sector: str) -> dict:
    """Returns the sector ETF's trailing P/E as a baseline, or None if unmapped."""
    etf = SECTOR_ETF_MAP.get(sector)
    if not etf or yf is None:
        return {"etf": etf, "pe": None}
    info = yf.Ticker(etf).info
    return {"etf": etf, "pe": info.get("trailingPE")}


def compare_to_sector(ticker: str, ticker_pe: float, sector: str) -> dict:
    """
    Returns how a stock's P/E compares to its sector baseline.
    premium_pct > 0 means the stock is priced ABOVE its sector's typical multiple.
    """
    baseline = get_sector_pe(sector)
    if not baseline["pe"] or not ticker_pe:
        return {"ticker": ticker, "sector": sector, "sector_etf": baseline["etf"],
                "sector_pe": baseline["pe"], "ticker_pe": ticker_pe, "premium_pct": None}

    premium_pct = (ticker_pe - baseline["pe"]) / baseline["pe"] * 100
    return {
        "ticker": ticker,
        "sector": sector,
        "sector_etf": baseline["etf"],
        "sector_pe": round(baseline["pe"], 2),
        "ticker_pe": round(ticker_pe, 2),
        "premium_pct": round(premium_pct, 1),
    }
