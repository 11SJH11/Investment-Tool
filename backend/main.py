"""
main.py

Local API for the portfolio analysis tool. Runs entirely on your machine --
no data leaves your computer except calls out to Yahoo Finance for price/
fundamentals data.

Run: uvicorn main:app --reload --port 8000
Then open frontend/ (see its README) or hit these endpoints directly.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import math
import sys
import os
from pathlib import Path
from datetime import date
import pandas as pd
from dotenv import load_dotenv

# Load .env explicitly from the same folder as this file, regardless of where
# the process was launched from -- avoids auto-discovery inconsistencies.
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

print(f"[startup] .env found: {_ENV_PATH.exists()}", file=sys.stderr)
print(f"[startup] FRED_API_KEY loaded: {'yes' if os.environ.get('FRED_API_KEY') else 'no'}", file=sys.stderr)
print(f"[startup] ANTHROPIC_API_KEY loaded: {'yes' if os.environ.get('ANTHROPIC_API_KEY') else 'no'}", file=sys.stderr)

from data_fetcher import fetch_multiple, get_price_on_date, get_current_price
from fundamentals import fetch_fundamentals_multiple, METRIC_MAP
from classify import classify_multiple
from diversification import correlation_matrix, diversification_flags
from backtest import compare_to_benchmark
from portfolio import Portfolio
import metrics as metrics_module
from macro import get_macro_snapshot
from sector_valuation import compare_to_sector
from stress_test import run_stress_test
from consistency_agent import review_journal
from risk_screener import evaluate_multiple, list_criteria, PRESETS
from indicators import list_indicators, compute_indicator
from market_scanner import start_scan, get_scan_status, TICKER_UNIVERSES
from watchlist import load_watchlist, add_ticker as wl_add, remove_ticker as wl_remove, fetch_watchlist_data

app = FastAPI(title="Portfolio Analysis API")

# Local-only tool -- CORS wide open is fine since nothing leaves your machine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def clean_json(obj):
    """Recursively replace NaN/inf with None so FastAPI's JSON encoder doesn't choke."""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/classify")
def classify(tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,JNJ,GLD")):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    try:
        df = classify_multiple(ticker_list)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Classification fetch failed: {e}")
    return clean_json(df.reset_index().to_dict(orient="records"))


@app.get("/api/fundamentals")
def fundamentals(tickers: str = Query(...)):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    try:
        df = fetch_fundamentals_multiple(ticker_list)
        classification_df = classify_multiple(ticker_list)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fundamentals fetch failed: {e}")

    result = {}
    for t in ticker_list:
        row = df[t].to_dict() if t in df.columns else {}
        cls = classification_df.loc[t].to_dict() if t in classification_df.index else {}
        result[t] = {
            "name": cls.get("name", t),
            "asset_class": cls.get("asset_class", "Unknown"),
            "sector": cls.get("sector", "N/A"),
            "industry": cls.get("industry", "N/A"),
            "metrics": row,
        }
    return clean_json(result)


@app.get("/api/diversification")
def diversification(tickers: str = Query(...), start: str = "2022-01-01", threshold: float = 0.5):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    try:
        price_data = fetch_multiple(ticker_list, start=start)
        classification_df = classify_multiple(ticker_list)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {e}")

    corr = correlation_matrix(price_data)
    flags = diversification_flags(price_data, threshold)

    enriched_flags = []
    for f in flags:
        t1, t2 = f["pair"]
        reason = None
        if t1 in classification_df.index and t2 in classification_df.index:
            s1, s2 = classification_df.loc[t1, "sector"], classification_df.loc[t2, "sector"]
            c1, c2 = classification_df.loc[t1, "asset_class"], classification_df.loc[t2, "asset_class"]
            if s1 == s2 and s1 != "N/A":
                reason = f"Both {s1} sector"
            elif c1 == c2:
                reason = f"Both {c1}"
        enriched_flags.append({"ticker_a": t1, "ticker_b": t2,
                                "correlation": f["correlation"], "reason": reason})

    return clean_json({
        "correlation_matrix": corr.round(3).to_dict(),
        "flags": enriched_flags,
        "tickers": ticker_list,
    })


class BacktestRequest(BaseModel):
    tickers: list[str]
    target_allocation: dict[str, float]
    monthly_contribution: float
    benchmark_ticker: str
    start: str = "2018-01-01"
    rebalance_freq: Optional[str] = "Q"


@app.post("/api/backtest")
def backtest(req: BacktestRequest):
    total_weight = sum(req.target_allocation.values())
    if abs(total_weight - 1.0) > 0.01:
        raise HTTPException(status_code=400, detail=f"Allocation must sum to 1.0 (got {total_weight:.3f})")

    all_tickers = list(set(req.tickers) | {req.benchmark_ticker})
    try:
        price_data = fetch_multiple(all_tickers, start=req.start)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {e}")

    try:
        comparison = compare_to_benchmark(
            price_data, req.target_allocation, req.monthly_contribution,
            req.benchmark_ticker, req.rebalance_freq,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return clean_json({
        "strategy_perf": comparison["strategy"],
        "benchmark_perf": comparison["benchmark"],
        "strategy_curve": [
            {"date": str(d.date()), "value": v}
            for d, v in comparison["strategy_curve"].items()
        ],
        "benchmark_curve": [
            {"date": str(d.date()), "value": v}
            for d, v in comparison["benchmark_curve"].items()
        ],
    })


@app.get("/api/portfolio")
def get_portfolio():
    p = Portfolio.load()
    holdings = p.holdings_summary()
    return clean_json({
        "target_allocation": p.target_allocation,
        "holdings": holdings,
        "contributions": [vars(c) for c in p.contributions],
    })


@app.get("/api/portfolio/contributions")
def get_contributions_detail():
    """Per-transaction detail: price paid then vs. price now, plus your note/exit_condition."""
    p = Portfolio.load()
    tickers = list(set(c.ticker for c in p.contributions))
    if not tickers:
        return clean_json({"contributions": []})
    try:
        price_data = fetch_multiple(tickers, start="2024-01-01")
        latest_prices = price_data.iloc[-1].to_dict()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {e}")
    return clean_json({"contributions": p.contributions_detail(latest_prices)})


@app.get("/api/price-on-date")
def price_on_date(ticker: str, date: str):
    """Preview the price that WOULD be auto-filled for a given ticker/date, before you submit."""
    try:
        return clean_json(get_price_on_date(ticker.upper(), date))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/current-price")
def current_price(ticker: str):
    try:
        return clean_json({"ticker": ticker.upper(), "price": get_current_price(ticker.upper())})
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ContributionRequest(BaseModel):
    ticker: str
    amount: float
    date: Optional[str] = None
    price: Optional[float] = None
    note: Optional[str] = ""
    exit_condition: Optional[str] = ""


@app.post("/api/portfolio/contribution")
def add_contribution(req: ContributionRequest):
    p = Portfolio.load()
    on_date = req.date or date.today().isoformat()

    price = req.price
    if price is None:
        try:
            price_info = get_price_on_date(req.ticker.upper(), on_date)
            price = price_info["price"]
            on_date = price_info["date_used"]
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Couldn't fetch price for {req.ticker} on {on_date}: {e}")

    p.add_contribution(req.ticker.upper(), req.amount, price, on_date, req.note or "", req.exit_condition or "")
    p.save()
    return clean_json({"status": "saved", "price_used": price, "date_used": on_date})


class TargetAllocationRequest(BaseModel):
    allocation: dict[str, float]


@app.post("/api/portfolio/target")
def set_target(req: TargetAllocationRequest):
    p = Portfolio.load()
    try:
        p.set_target_allocation(req.allocation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    p.save()
    return {"status": "saved"}


@app.get("/api/portfolio/value")
def portfolio_value():
    p = Portfolio.load()
    tickers = list(p.holdings_summary().keys())
    if not tickers:
        return clean_json({"holdings": {}, "rebalance_flags": []})
    try:
        price_data = fetch_multiple(tickers, start="2024-01-01")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {e}")

    latest_prices = price_data.iloc[-1].to_dict()
    current = p.current_value(latest_prices)
    suggestions = p.rebalance_suggestions(latest_prices)
    return clean_json({"holdings": current, "rebalance_flags": suggestions})


@app.get("/api/macro")
def macro():
    try:
        return clean_json(get_macro_snapshot())
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Macro data fetch failed: {e}")


@app.get("/api/sector-valuation")
def sector_valuation(tickers: str = Query(...)):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    try:
        fundamentals_df = fetch_fundamentals_multiple(ticker_list)
        classification_df = classify_multiple(ticker_list)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {e}")

    results = []
    for t in ticker_list:
        if t not in classification_df.index:
            continue
        sector = classification_df.loc[t, "sector"]
        pe = fundamentals_df[t].get("P/E Ratio (trailing)") if t in fundamentals_df.columns else None
        results.append(compare_to_sector(t, pe, sector))

    return clean_json({"results": results})


class StressTestRequest(BaseModel):
    market_move_pct: float = -20.0


@app.post("/api/stress-test")
def stress_test(req: StressTestRequest):
    p = Portfolio.load()
    tickers = list(p.holdings_summary().keys())
    if not tickers:
        return clean_json({"holdings": {}, "portfolio_estimated_move_pct": None})
    try:
        price_data = fetch_multiple(tickers, start="2024-01-01")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Price fetch failed: {e}")

    latest_prices = price_data.iloc[-1].to_dict()
    current = p.current_value(latest_prices)
    holdings_value = {t: v["value"] for t, v in current.items()}

    try:
        result = run_stress_test(holdings_value, req.market_move_pct)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stress test failed: {e}")
    return clean_json(result)


@app.post("/api/journal/review")
def review_journal_endpoint():
    """
    Reviews your reasoning (now logged directly on each contribution) against
    current holdings/metrics. Also includes any legacy standalone journal
    entries from before notes were merged into the contribution form.
    """
    p = Portfolio.load()
    tickers = list(p.holdings_summary().keys())
    if not tickers:
        return clean_json({"flags": [], "summary": "No holdings yet -- nothing to check."})

    try:
        price_data = fetch_multiple(tickers, start="2024-01-01")
        fundamentals_df = fetch_fundamentals_multiple(tickers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {e}")

    latest_prices = price_data.iloc[-1].to_dict()
    current_holdings = p.current_value(latest_prices)
    current_metrics = {t: fundamentals_df[t].to_dict() for t in tickers if t in fundamentals_df.columns}

    journal_entries = [
        {"date": c.date, "ticker": c.ticker, "note": c.note, "exit_condition": c.exit_condition}
        for c in p.contributions if c.note or c.exit_condition
    ] + [vars(j) for j in p.journal]

    try:
        result = review_journal(journal_entries, current_metrics, current_holdings)
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent review failed: {e}")

    return clean_json(result)


class RiskScreenRequest(BaseModel):
    tickers: list[str]
    profile: str = "low"
    overrides: Optional[dict] = None


@app.get("/api/risk-criteria")
def risk_criteria():
    """All available screening criteria (for the Custom builder) plus the 3 presets."""
    return clean_json({
        "criteria": list_criteria(),
        "presets": {k: {"label": v["label"], "criteria": v["criteria"]} for k, v in PRESETS.items()},
    })


@app.post("/api/risk-screen")
def risk_screen(req: RiskScreenRequest):
    try:
        results = evaluate_multiple(req.tickers, req.profile, req.overrides)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Risk screen failed: {e}")
    return clean_json({"results": results})


@app.get("/api/indicators")
def get_indicators():
    return clean_json({"indicators": list_indicators()})


# ---------------------------------------------------------------------------
# Market scanner: screens a whole ticker universe (not just tickers you pick)
# against risk-screen criteria -- either a preset or a fully custom list of
# criteria you built yourself. Runs as a background job since scanning
# hundreds of tickers via yfinance takes real time (this is a genuine
# constraint of free data sources, not a bug) -- start it, then poll status.
# ---------------------------------------------------------------------------

class CriterionOverride(BaseModel):
    key: str
    value: float | bool


class ScanRequest(BaseModel):
    universe: str = "sp500"
    profile: str = "low"                              # ignored if criteria is set (custom mode)
    overrides: Optional[dict] = None
    criteria: Optional[list[CriterionOverride]] = None  # custom mode: your own picked criteria + values
    min_criteria_passed: Optional[int] = None


@app.get("/api/scan/universes")
def scan_universes():
    return clean_json({
        "universes": [{"key": k, "label": v["label"], "count": len(v["tickers"])}
                       for k, v in TICKER_UNIVERSES.items()]
    })


@app.post("/api/scan/start")
def scan_start(req: ScanRequest):
    if req.universe not in TICKER_UNIVERSES:
        raise HTTPException(status_code=400, detail=f"Unknown universe: {req.universe}")
    criteria_list = [{"key": c.key, "value": c.value} for c in req.criteria] if req.criteria else None
    job_id = start_scan(req.universe, req.profile, req.overrides, req.min_criteria_passed, criteria_list)
    return clean_json({"job_id": job_id})


@app.get("/api/scan/status/{job_id}")
def scan_status(job_id: str):
    status = get_scan_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return clean_json(status)


# ---------------------------------------------------------------------------
# Watchlist: a small editable ticker list, separate from your real holdings.
# ---------------------------------------------------------------------------

@app.get("/api/watchlist")
def get_watchlist():
    return clean_json({"tickers": load_watchlist()})


class WatchlistTickerRequest(BaseModel):
    ticker: str


@app.post("/api/watchlist/add")
def watchlist_add(req: WatchlistTickerRequest):
    return clean_json({"tickers": wl_add(req.ticker)})


@app.post("/api/watchlist/remove")
def watchlist_remove(req: WatchlistTickerRequest):
    return clean_json({"tickers": wl_remove(req.ticker)})


@app.get("/api/watchlist/data")
def watchlist_data():
    tickers = load_watchlist()
    if not tickers:
        return clean_json({"data": []})
    try:
        return clean_json({"data": fetch_watchlist_data(tickers)})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Watchlist data fetch failed: {e}")
