"""
market_scanner.py

Scans a whole ticker universe (not just tickers you type in) against
risk_screener criteria, so you don't have to know in advance which tickers
to check.

Honest constraint, worth knowing: there is no free source for "every stock
on every exchange" that's practical to scan in real time -- that's
genuinely paid, professional-grade infrastructure (Bloomberg, Polygon.io,
etc.). What's realistic here is a large, liquid, well-known universe: the
S&P 500 (500 large US companies) plus the bonds/commodities/futures we
already track elsewhere in the app. That's a real, useful "the market" for
almost all practical purposes -- just not literally every ticker that exists.

Scanning even 500 tickers one at a time via yfinance takes real time (each
call is a network round-trip) and can hit rate limits if done too
aggressively. This runs as a background job with a thread pool: call
start_scan() to kick it off, poll get_scan_status(job_id) for progress and
results as they come in.
"""

import threading
import uuid
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from risk_screener import evaluate_ticker, evaluate_ticker_custom

SP500_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "BRK-B", "AVGO", "TSLA",
    "JPM", "LLY", "V", "UNH", "XOM", "MA", "COST", "HD", "PG", "JNJ",
    "NFLX", "BAC", "ABBV", "CRM", "WMT", "KO", "CVX", "MRK", "ADBE", "PEP",
    "AMD", "TMO", "ORCL", "LIN", "ACN", "MCD", "CSCO", "WFC", "ABT", "IBM",
    "GE", "DHR", "TXN", "PM", "CAT", "VZ", "INTU", "NOW", "ISRG", "QCOM",
    "AMGN", "DIS", "AMAT", "CMCSA", "SPGI", "UNP", "PFE", "GS", "RTX", "NEE",
    "LOW", "BKNG", "T", "HON", "UBER", "COP", "SYK", "ELV", "MS", "PGR",
    "BLK", "TJX", "VRTX", "SCHW", "MDT", "LMT", "PLD", "C", "ETN", "MU",
    "ADP", "BSX", "REGN", "CB", "MMC", "BA", "ADI", "GILD", "SBUX", "PANW",
    "AMT", "ANET", "KLAC", "DE", "SO", "LRCX", "FI", "ICE", "MO", "CI",
    "DUK", "SHW", "ZTS", "BX", "EQIX", "CME", "WM", "APH", "NKE", "PYPL",
    "MDLZ", "SNPS", "PH", "ITW", "CDNS", "CMG", "TT", "AON", "MCK", "CTAS",
    "USB", "ECL", "PNC", "MSI", "NOC", "EMR", "FCX", "APD", "COF", "MAR",
    "CL", "ROP", "ORLY", "TDG", "PSA", "AJG", "GD", "WELL", "SPG", "TGT",
    "MMM", "CARR", "PCAR", "ADSK", "AFL", "OXY", "SRE", "NSC", "MET", "AZO",
    "F", "GM", "HLT", "JCI", "TRV", "AIG", "URI", "KMB", "FDX", "PSX",
    "DLR", "O", "AEP", "D", "COIN", "PAYX", "ROST", "MPC", "MSCI", "PCG",
    "KMI", "CTVA", "NEM", "PRU", "VLO", "FAST", "GWW", "ALL", "OTIS", "IDXX",
    "A", "CMI", "EW", "CPRT", "AMP", "YUM", "DHI", "DOW", "PPG", "ODFL",
    "EXC", "XEL", "CSGP", "HES", "KR", "BK", "CNC", "VRSK", "GEHC", "SYY",
]

FUTURES_TICKERS = ["ES=F", "GC=F", "CL=F", "NG=F", "ZN=F", "SI=F", "ZC=F", "ZS=F", "6E=F", "6J=F"]

BONDS_TICKERS = ["BND", "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"]

COMMODITIES_TICKERS = ["GLD", "SLV", "DBC", "USO", "UNG"]

TICKER_UNIVERSES = {
    "sp500": {"label": "Large-cap US stocks (~200, S&P 500-heavy)", "tickers": SP500_TICKERS},
    "futures": {"label": "Common liquid futures contracts", "tickers": FUTURES_TICKERS},
    "bonds": {"label": "Bond ETFs", "tickers": BONDS_TICKERS},
    "commodities": {"label": "Commodity ETFs", "tickers": COMMODITIES_TICKERS},
    "sp500_plus_alts": {
        "label": "S&P 500 + bonds + commodities + futures",
        "tickers": SP500_TICKERS + BONDS_TICKERS + COMMODITIES_TICKERS + FUTURES_TICKERS,
    },
}

_JOBS = {}
_JOBS_LOCK = threading.Lock()

MAX_WORKERS = 10


def _run_scan(job_id: str, tickers: list, profile: str, overrides: dict, min_criteria_passed: int,
              criteria_list: list = None):
    total = len(tickers)
    passed_results = []
    errors = []

    def evaluate_one(t):
        if criteria_list is not None:
            return evaluate_ticker_custom(t, criteria_list)
        return evaluate_ticker(t, profile, overrides)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(evaluate_one, t): t for t in tickers}
        completed = 0
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            completed += 1
            try:
                result = future.result()
                if min_criteria_passed is None or result["passed_count"] >= min_criteria_passed:
                    passed_results.append(result)
            except Exception as e:
                errors.append({"ticker": ticker, "error": str(e)})

            with _JOBS_LOCK:
                _JOBS[job_id]["scanned"] = completed
                _JOBS[job_id]["total"] = total
                _JOBS[job_id]["matches_so_far"] = len(passed_results)

    passed_results.sort(key=lambda r: r["passed_count"], reverse=True)

    with _JOBS_LOCK:
        _JOBS[job_id]["status"] = "done"
        _JOBS[job_id]["results"] = passed_results
        _JOBS[job_id]["errors"] = errors
        _JOBS[job_id]["finished_at"] = time.time()


def start_scan(universe: str, profile: str, overrides: dict = None, min_criteria_passed: int = None,
               criteria_list: list = None) -> str:
    tickers = TICKER_UNIVERSES[universe]["tickers"]
    job_id = str(uuid.uuid4())

    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "universe": universe,
            "profile": profile if criteria_list is None else "custom",
            "scanned": 0,
            "total": len(tickers),
            "matches_so_far": 0,
            "results": None,
            "errors": [],
            "started_at": time.time(),
        }

    thread = threading.Thread(
        target=_run_scan, args=(job_id, tickers, profile, overrides, min_criteria_passed, criteria_list),
        daemon=True,
    )
    thread.start()
    return job_id


def get_scan_status(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
