"""
stress_test.py

Estimates how your CURRENT portfolio would likely respond to a hypothetical
broad market move, using each holding's beta (volatility relative to the
market). This is a rough estimate, not a prediction -- beta is a historical
average relationship, not a guarantee of how any specific future drop plays
out. But it's a genuinely useful gut-check: "given how my holdings have
behaved relative to the market historically, roughly how exposed am I?"
"""

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_betas(tickers: list) -> dict:
    """Returns {ticker: beta}, using 1.0 (market-average) as a fallback if missing."""
    betas = {}
    for t in tickers:
        if yf is None:
            betas[t] = 1.0
            continue
        info = yf.Ticker(t).info
        beta = info.get("beta")
        betas[t] = beta if beta is not None else 1.0
    return betas


def run_stress_test(holdings_value: dict, market_move_pct: float = -20.0) -> dict:
    """
    holdings_value: {ticker: current_dollar_value}
    market_move_pct: hypothetical broad market move, e.g. -20 for a 20% drop

    Returns per-holding estimated impact and total portfolio estimated impact,
    using estimated_move = beta * market_move_pct.
    """
    tickers = list(holdings_value.keys())
    if not tickers:
        return {"market_move_pct": market_move_pct, "holdings": {}, "portfolio_estimated_move_pct": None}

    betas = get_betas(tickers)
    total_value = sum(holdings_value.values())

    per_holding = {}
    weighted_move = 0.0
    for t in tickers:
        beta = betas.get(t, 1.0)
        estimated_move_pct = beta * market_move_pct
        value = holdings_value[t]
        estimated_dollar_change = value * (estimated_move_pct / 100)
        weight = value / total_value if total_value else 0
        weighted_move += weight * estimated_move_pct

        per_holding[t] = {
            "beta": round(beta, 2),
            "current_value": round(value, 2),
            "portfolio_weight_pct": round(weight * 100, 1),
            "estimated_move_pct": round(estimated_move_pct, 1),
            "estimated_dollar_change": round(estimated_dollar_change, 2),
        }

    return {
        "market_move_pct": market_move_pct,
        "holdings": per_holding,
        "portfolio_estimated_move_pct": round(weighted_move, 1),
        "portfolio_estimated_dollar_change": round(total_value * (weighted_move / 100), 2),
        "total_value": round(total_value, 2),
    }
