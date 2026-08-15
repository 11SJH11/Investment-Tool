"""
metrics.py

Standard performance/risk metrics so you can judge a strategy honestly
instead of just eyeballing a line going up.
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq


def daily_returns(price_series: pd.Series) -> pd.Series:
    return price_series.pct_change().dropna()


def cagr(price_series: pd.Series) -> float:
    """Compound annual growth rate."""
    start, end = price_series.iloc[0], price_series.iloc[-1]
    years = (price_series.index[-1] - price_series.index[0]).days / 365.25
    if years <= 0 or start <= 0:
        return float("nan")
    return (end / start) ** (1 / years) - 1


def annualized_volatility(price_series: pd.Series) -> float:
    returns = daily_returns(price_series)
    return returns.std() * np.sqrt(252)


def max_drawdown(price_series: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative percentage."""
    cumulative_max = price_series.cummax()
    drawdown = (price_series - cumulative_max) / cumulative_max
    return drawdown.min()


def sharpe_ratio(price_series: pd.Series, risk_free_rate: float = 0.04) -> float:
    """
    Risk-adjusted return. Higher is better; above ~1.0 is generally considered
    good, above ~2.0 is very good. Uses a default 4% risk-free rate (adjust
    to current T-bill yield if you want precision).
    """
    returns = daily_returns(price_series)
    excess_daily = returns - (risk_free_rate / 252)
    if returns.std() == 0:
        return float("nan")
    return (excess_daily.mean() / returns.std()) * np.sqrt(252)


def summarize(price_series: pd.Series, label: str = "") -> dict:
    return {
        "label": label,
        "cagr_pct": round(cagr(price_series) * 100, 2),
        "annual_volatility_pct": round(annualized_volatility(price_series) * 100, 2),
        "max_drawdown_pct": round(max_drawdown(price_series) * 100, 2),
        "sharpe_ratio": round(sharpe_ratio(price_series), 2),
        "total_return_pct": round((price_series.iloc[-1] / price_series.iloc[0] - 1) * 100, 2),
    }


def money_weighted_annual_return(cash_flow_dates: list, cash_flow_amounts: list) -> float:
    """
    Computes the annualized money-weighted return (IRR) for a series of cash
    flows -- e.g. monthly contributions (negative, money going in) followed
    by a final portfolio value (positive, money you'd have if you cashed out).

    This is the correct way to measure "return" when you're contributing
    money over time, unlike a plain CAGR on portfolio value (which is
    distorted by the fact that the portfolio starts near zero and grows
    partly because you're ADDING cash, not just from market gains).
    """
    t0 = cash_flow_dates[0]
    years = np.array([(d - t0).days / 365.25 for d in cash_flow_dates])
    amounts = np.array(cash_flow_amounts)

    def npv(rate):
        return np.sum(amounts / (1 + rate) ** years)

    try:
        return brentq(npv, -0.99, 10)
    except ValueError:
        return float("nan")


def print_summary(summary: dict):
    print(f"--- {summary['label']} ---")
    print(f"  Total return:       {summary['total_return_pct']:>8.2f}%")
    print(f"  CAGR:               {summary['cagr_pct']:>8.2f}%")
    print(f"  Annual volatility:  {summary['annual_volatility_pct']:>8.2f}%")
    print(f"  Max drawdown:       {summary['max_drawdown_pct']:>8.2f}%")
    print(f"  Sharpe ratio:       {summary['sharpe_ratio']:>8.2f}")
