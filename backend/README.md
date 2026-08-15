# Portfolio Analysis Tool (Prototype v0)

A personal investment **decision-support** tool. It does NOT execute trades
or move money — you stay in control of every transaction. What it does:

- Pulls historical price data for stocks/ETFs/crypto (via `yfinance`)
- Tracks your actual contributions and holdings
- Backtests a target allocation strategy against real market history
- Compares your strategy to a simple benchmark (e.g. just buying SPY)
- Flags when your portfolio has drifted from target and needs rebalancing
- Reports honest metrics: annualized (money-weighted) return, max drawdown

## Why money-weighted return, not simple % gain?

When you're contributing money regularly, a plain "portfolio value grew
X%" number is misleading — it's inflated by the fact that you kept adding
cash, not just by market performance. This tool uses IRR (internal rate of
return) on your actual cash flows, which is the correct way to answer
"what annual return am I actually getting on my money?"

## Setup

```bash
pip install -r requirements.txt
```

## Quick start (synthetic data demo — no network needed)

```bash
python3 demo.py
```

This runs the full pipeline on made-up price data so you can see the
mechanics work. **Do not use this to evaluate real strategies** — it's
just to prove the code runs correctly.

## Using real data

```python
from data_fetcher import fetch_multiple
from backtest import compare_to_benchmark

# Real tickers, e.g. broad market ETF, tech ETF, bonds, crypto
tickers = ["VOO", "QQQ", "BND", "BTC-USD"]
prices = fetch_multiple(tickers, start="2018-01-01")

target_allocation = {
    "VOO": 0.55,
    "QQQ": 0.15,
    "BND": 0.20,
    "BTC-USD": 0.10,
}

result = compare_to_benchmark(
    prices, target_allocation,
    monthly_contribution=500,
    benchmark_ticker="VOO",
    rebalance_freq="Q",   # 'Q' quarterly, 'M' monthly, 'A' annual, None = never
)

print(result["strategy"])
print(result["benchmark"])
```

## Tracking your real portfolio over time

```python
from portfolio import Portfolio

p = Portfolio.load()  # loads portfolio_state.json if it exists, else starts fresh
p.set_target_allocation({"VOO": 0.55, "QQQ": 0.15, "BND": 0.20, "BTC-USD": 0.10})

# Each time you actually invest money, log it:
p.add_contribution(ticker="VOO", amount=275, price=550.20)

# Check current state against live prices:
latest_prices = {"VOO": 555.10, "QQQ": 480.00, "BND": 72.10, "BTC-USD": 61000}
print(p.current_value(latest_prices))
print(p.rebalance_suggestions(latest_prices))

p.save()  # persists to portfolio_state.json
```

## Known limitations (v0 — things to improve next)

- No transaction costs or tax modeling (capital gains, dividends) yet
- Backtest assumes contributions land exactly on the first trading day of
  the month — fine for testing, not perfectly realistic
- No support for fractional-share restrictions some brokers impose
- Risk-free rate in Sharpe calc is hardcoded — could pull live T-bill yield
- No web/mobile UI yet — this is the analysis engine, dashboard comes next
- Crypto volatility assumptions in demo data are illustrative, not
  calibrated to real crypto behavior

## Files

| File | Purpose |
|---|---|
| `data_fetcher.py` | Pulls & caches real historical price data |
| `demo_data.py` | Synthetic data generator, for offline testing only |
| `portfolio.py` | Tracks your real holdings/contributions, no real money moved |
| `metrics.py` | Return, volatility, drawdown, Sharpe, IRR calculations |
| `backtest.py` | Simulates a strategy over history with contributions + rebalancing |
| `demo.py` | End-to-end example run |

## Important

This tool is for your own analysis and learning. It is not financial
advice, and past backtested performance — synthetic or real — does not
predict future results. Treat any strategy's backtest results as one
input among several, not a guarantee.
