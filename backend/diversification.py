"""
diversification.py

Checks how correlated a set of tickers actually are. Picking 3 different
company names doesn't mean you're diversified if they all move together
(common with tech stocks, which tend to rise and fall as a group based on
broad sector sentiment, rate expectations, etc.)
"""

import pandas as pd


def correlation_matrix(price_data: pd.DataFrame) -> pd.DataFrame:
    """
    price_data: columns = tickers, index = dates, values = close price
    Returns the pairwise correlation of daily returns (-1 to 1).
    1.0 = move in perfect lockstep, 0 = unrelated, -1.0 = move opposite.
    """
    returns = price_data.pct_change().dropna()
    return returns.corr()


def diversification_flags(price_data: pd.DataFrame, threshold: float = 0.75) -> list:
    """
    Flags ticker pairs with correlation above the threshold -- a signal
    that holding both doesn't add much diversification benefit.
    """
    corr = correlation_matrix(price_data)
    flags = []
    tickers = corr.columns.tolist()
    for i, t1 in enumerate(tickers):
        for t2 in tickers[i + 1:]:
            c = corr.loc[t1, t2]
            if c >= threshold:
                flags.append({"pair": (t1, t2), "correlation": round(c, 2)})
    return flags


def print_diversification_report(price_data: pd.DataFrame, threshold: float = 0.75, classification_df=None):
    corr = correlation_matrix(price_data)
    print("Correlation matrix (daily returns):")
    print(corr.round(2).to_string())

    flags = diversification_flags(price_data, threshold)
    print(f"\nPairs with correlation >= {threshold} (limited diversification benefit):")
    if flags:
        for f in flags:
            t1, t2 = f["pair"]
            reason = ""
            if classification_df is not None and t1 in classification_df.index and t2 in classification_df.index:
                c1 = classification_df.loc[t1, "asset_class"]
                c2 = classification_df.loc[t2, "asset_class"]
                s1 = classification_df.loc[t1, "sector"]
                s2 = classification_df.loc[t2, "sector"]
                if s1 == s2 and s1 != "N/A":
                    reason = f"  (both {s1} sector)"
                elif c1 == c2:
                    reason = f"  (both {c1})"
            print(f"  {t1} <-> {t2}: {f['correlation']}{reason}")
    else:
        print("  None -- your picks move fairly independently of each other.")
