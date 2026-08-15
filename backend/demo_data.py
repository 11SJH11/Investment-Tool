"""
demo_data.py

Generates realistic-ish synthetic price data so you can test the tool
without hitting a live API. This is ONLY for testing the mechanics of the
tool -- do not use this data to evaluate any real strategy. Swap in
data_fetcher.py's real historical data for actual decisions.
"""

import numpy as np
import pandas as pd


def generate_synthetic_prices(tickers_params: dict, start: str = "2015-01-01",
                                end: str = "2025-01-01", seed: int = 42) -> pd.DataFrame:
    """
    tickers_params: {ticker: {'annual_return': 0.08, 'annual_vol': 0.15, 'start_price': 100}}
    Uses geometric Brownian motion -- simplistic but fine for testing mechanics.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n = len(dates)
    data = {}
    for ticker, params in tickers_params.items():
        mu = params.get("annual_return", 0.08)
        sigma = params.get("annual_vol", 0.15)
        s0 = params.get("start_price", 100)
        dt = 1 / 252
        daily_drift = (mu - 0.5 * sigma ** 2) * dt
        daily_shocks = rng.normal(loc=daily_drift, scale=sigma * np.sqrt(dt), size=n)
        log_prices = np.log(s0) + np.cumsum(daily_shocks)
        data[ticker] = np.exp(log_prices)
    return pd.DataFrame(data, index=dates)
