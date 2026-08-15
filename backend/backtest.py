"""
backtest.py

Simulates a monthly-contribution, target-allocation strategy over historical
price data, with periodic rebalancing. This is the tool for sanity-checking
an idea (e.g. "70% VOO / 20% QQQ / 10% BTC-USD, rebalanced quarterly")
against real market history before committing real contributions to it.
"""

import pandas as pd
from metrics import summarize, money_weighted_annual_return, max_drawdown


def backtest_strategy(price_data: pd.DataFrame, target_allocation: dict,
                       monthly_contribution: float, rebalance_freq: str = "Q"):
    """
    price_data: DataFrame, columns = tickers, index = dates, values = close price
    target_allocation: {ticker: weight}, weights must sum to 1.0
    monthly_contribution: dollars added at the start of each month
    rebalance_freq: pandas offset alias, e.g. 'Q' (quarterly), 'M' (monthly), 'A' (annual), None to never rebalance

    Returns a DataFrame with a 'portfolio_value' column plus per-ticker
    share counts over time, and a metrics summary dict.
    """
    tickers = list(target_allocation.keys())
    missing = [t for t in tickers if t not in price_data.columns]
    if missing:
        raise ValueError(f"Missing price data for: {missing}")

    data = price_data[tickers].dropna()
    if data.empty:
        raise ValueError("No overlapping price data for the given tickers.")

    shares = {t: 0.0 for t in tickers}
    contributed_total = 0.0
    records = []

    # Determine contribution dates: first trading day of each month
    data = data.copy()
    data["month"] = data.index.to_period("M")
    contribution_dates = data.groupby("month").apply(lambda x: x.index.min())

    # Determine rebalance dates
    rebalance_dates = set()
    if rebalance_freq:
        data["rebal_period"] = data.index.to_period(rebalance_freq)
        rebalance_dates = set(data.groupby("rebal_period").apply(lambda x: x.index.min()).values)

    for current_date, row in data.iterrows():
        # Contribute new cash on the first trading day of the month
        if current_date in contribution_dates.values:
            contributed_total += monthly_contribution
            for t in tickers:
                dollars = monthly_contribution * target_allocation[t]
                shares[t] += dollars / row[t]

        # Rebalance to target weights if this is a rebalance date
        if current_date in rebalance_dates:
            total_value = sum(shares[t] * row[t] for t in tickers)
            if total_value > 0:
                for t in tickers:
                    target_value = total_value * target_allocation[t]
                    shares[t] = target_value / row[t]

        portfolio_value = sum(shares[t] * row[t] for t in tickers)
        records.append({"date": current_date, "portfolio_value": portfolio_value,
                         "contributed_total": contributed_total,
                         **{f"shares_{t}": shares[t] for t in tickers}})

    result = pd.DataFrame(records).set_index("date")

    final_value = result["portfolio_value"].iloc[-1]
    gain = final_value - contributed_total

    # Build cash flow series for a proper money-weighted (IRR) return:
    # each contribution is money leaving your pocket (negative), and the
    # final portfolio value is money you'd have if you cashed out today (positive).
    contrib_diff = result["contributed_total"].diff().fillna(result["contributed_total"].iloc[0])
    contribution_rows = result[contrib_diff > 0]
    cash_flow_dates = list(contribution_rows.index) + [result.index[-1]]
    cash_flow_amounts = [-monthly_contribution] * len(contribution_rows) + [final_value]
    annual_return = money_weighted_annual_return(cash_flow_dates, cash_flow_amounts)

    perf = {
        "label": "Strategy",
        "total_contributed": round(contributed_total, 2),
        "final_value": round(final_value, 2),
        "total_gain": round(gain, 2),
        "total_gain_pct_of_contributions": round(gain / contributed_total * 100, 2) if contributed_total else 0,
        "annualized_return_pct": round(annual_return * 100, 2),
        "max_drawdown_pct": round(max_drawdown(result["portfolio_value"]) * 100, 2),
    }

    return result, perf


def compare_to_benchmark(price_data: pd.DataFrame, target_allocation: dict,
                          monthly_contribution: float, benchmark_ticker: str,
                          rebalance_freq: str = "Q"):
    """
    Runs the same monthly-contribution schedule into a single benchmark ticker
    (e.g. 'SPY') so you can see if your custom allocation actually beats just
    buying the market.
    """
    bench_allocation = {benchmark_ticker: 1.0}
    strat_result, strat_perf = backtest_strategy(price_data, target_allocation,
                                                  monthly_contribution, rebalance_freq)
    bench_result, bench_perf = backtest_strategy(price_data, bench_allocation,
                                                   monthly_contribution, rebalance_freq=None)
    return {
        "strategy": strat_perf,
        "benchmark": bench_perf,
        "strategy_curve": strat_result["portfolio_value"],
        "benchmark_curve": bench_result["portfolio_value"],
    }
