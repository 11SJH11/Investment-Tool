"""
fundamentals.py

Pulls fundamental/valuation metrics (P/E, growth, margins, debt, etc.) for a
list of tickers via yfinance, so you can compare companies side by side
instead of guessing. This does NOT predict future performance -- it reports
current/recent public data only.
"""

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


# Metrics pulled from yfinance's .info dict, with human-readable labels
METRIC_MAP = {
    "trailingPE": "P/E Ratio (trailing)",
    "forwardPE": "P/E Ratio (forward)",
    "priceToBook": "Price/Book",
    "revenueGrowth": "Revenue Growth (YoY)",
    "earningsGrowth": "Earnings Growth (YoY)",
    "profitMargins": "Profit Margin",
    "operatingMargins": "Operating Margin",
    "debtToEquity": "Debt/Equity",
    "returnOnEquity": "Return on Equity",
    "freeCashflow": "Free Cash Flow",
    "marketCap": "Market Cap",
    "dividendYield": "Dividend Yield",
    "beta": "Beta (volatility vs market)",
    "fiftyTwoWeekHigh": "52-Week High",
    "fiftyTwoWeekLow": "52-Week Low",
}

PERCENT_METRICS = {"revenueGrowth", "earningsGrowth", "profitMargins",
                    "operatingMargins", "returnOnEquity", "dividendYield"}


def fetch_fundamentals(ticker: str) -> dict:
    """Returns a dict of raw fundamental metrics for one ticker."""
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")

    info = yf.Ticker(ticker).info
    result = {"ticker": ticker, "name": info.get("shortName", ticker)}
    for key in METRIC_MAP:
        result[key] = info.get(key)
    return result


def fetch_fundamentals_multiple(tickers: list) -> pd.DataFrame:
    """
    Returns a DataFrame: rows = metrics, columns = tickers.
    Easy to eyeball side by side.
    """
    rows = {}
    names = {}
    for t in tickers:
        data = fetch_fundamentals(t)
        names[t] = data["name"]
        rows[t] = {METRIC_MAP[k]: data[k] for k in METRIC_MAP}
    df = pd.DataFrame(rows)
    df.attrs["names"] = names
    return df


def format_comparison_table(df: pd.DataFrame) -> str:
    """
    Pretty-prints the comparison table with sensible formatting
    (percentages, currency-style numbers for market cap/FCF).
    """
    display_df = df.copy()

    def fmt_val(label, val):
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "n/a"
        if label == "Dividend Yield":
            # Yahoo Finance has inconsistently changed this field's units over time --
            # sometimes it's a decimal fraction (0.005 = 0.5%), sometimes it's already
            # in percentage-point form (0.51 = 0.51%). Heuristic: real dividend yields
            # are almost never above ~15%, so if the raw value is already that big,
            # assume it's already in percent form and don't multiply again.
            pct = val if val > 0.15 else val * 100
            return f"{pct:.2f}%"
        if label in ("Revenue Growth (YoY)", "Earnings Growth (YoY)", "Profit Margin",
                     "Operating Margin", "Return on Equity"):
            return f"{val * 100:.1f}%"
        if label in ("Market Cap", "Free Cash Flow"):
            if abs(val) >= 1e12:
                return f"${val / 1e12:.2f}T"
            if abs(val) >= 1e9:
                return f"${val / 1e9:.1f}B"
            return f"${val / 1e6:.1f}M"
        if label in ("P/E Ratio (trailing)", "P/E Ratio (forward)", "Price/Book",
                      "Debt/Equity", "Beta (volatility vs market)"):
            return f"{val:.2f}"
        return f"{val:.2f}" if isinstance(val, float) else str(val)

    for col in display_df.columns:
        display_df[col] = [fmt_val(idx, v) for idx, v in display_df[col].items()]

    return display_df.to_string()


def print_grouped_comparison(df: pd.DataFrame, classification_df: "pd.DataFrame"):
    """
    Prints the fundamentals table split into sections by asset class, and
    within Stocks, further split by sector. classification_df comes from
    classify.classify_multiple().
    """
    for asset_class in classification_df["asset_class"].unique():
        tickers_in_class = classification_df[classification_df["asset_class"] == asset_class].index.tolist()
        cols_present = [t for t in tickers_in_class if t in df.columns]
        if not cols_present:
            continue

        print(f"\n{'=' * 70}\n{asset_class.upper()}\n{'=' * 70}")

        if asset_class == "Stock":
            # Further split stocks by sector for readability
            sub = classification_df.loc[cols_present]
            for sector in sub["sector"].unique():
                sector_tickers = sub[sub["sector"] == sector].index.tolist()
                print(f"\n  -- Sector: {sector} --")
                print(format_comparison_table(df[sector_tickers]))
        else:
            print(format_comparison_table(df[cols_present]))
