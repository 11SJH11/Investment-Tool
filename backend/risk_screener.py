"""
risk_screener.py

A plugin-style registry for screening criteria, mirroring indicators.py's
pattern. To add a new criterion, write a function, decorate it with
@criterion(...), and it's automatically available everywhere -- in presets,
in custom screens, and in the frontend's "Custom" builder (which reads the
list dynamically from /api/risk-criteria, no frontend code changes needed).

Presets (low/medium/high) are just named, fixed selections of criteria with
default parameter values. "Custom" mode is the exact same machinery with a
user-chosen subset of criteria and user-chosen parameter values -- there is
no separate code path, which is why adding one new criterion automatically
makes it available as a custom option too.

This never outputs a single "score" or verdict, and passing criteria is NOT
a prediction of future performance -- it only means the ticker fits a
checkable profile you defined. Use it to narrow a list for further
research, not as a buy signal.
"""

try:
    import yfinance as yf
except ImportError:
    yf = None


CRITERIA_REGISTRY = {}


def criterion(key: str, label_template: str, default_value, param_type: str = "number"):
    """
    Decorator to register a screening criterion.
    key: unique identifier, e.g. "max_beta"
    label_template: human-readable label with {value} placeholder for the
                     current threshold, e.g. "Beta <= {value}"
    default_value: the default threshold if not overridden
    param_type: "number" (for now; room to grow, e.g. "bool" later)

    The decorated function takes (metrics: dict, value) and returns
    True/False/None (None = "can't be evaluated, missing data").
    """
    def decorator(func):
        CRITERIA_REGISTRY[key] = {
            "func": func, "label_template": label_template,
            "default_value": default_value, "param_type": param_type,
        }
        return func
    return decorator


def list_criteria() -> list:
    """All available criteria, for the frontend's Custom builder to render checkboxes from."""
    return [
        {"key": k, "label": v["label_template"].format(value=v["default_value"]),
         "default_value": v["default_value"], "param_type": v["param_type"]}
        for k, v in CRITERIA_REGISTRY.items()
    ]


PRESETS = {
    "low": {
        "label": "Low risk (capital preservation)",
        "criteria": [
            {"key": "max_beta", "value": 0.8},
            {"key": "max_debt_equity", "value": 100},
            {"key": "min_market_cap", "value": 10e9},
            {"key": "positive_fcf", "value": True},
            {"key": "positive_margin", "value": True},
        ],
    },
    "medium": {
        "label": "Medium risk (growth-tilted)",
        "criteria": [
            {"key": "min_beta", "value": 1.0},
            {"key": "max_beta", "value": 1.6},
            {"key": "min_revenue_growth", "value": 0.15},
            {"key": "max_debt_equity", "value": 150},
            {"key": "min_market_cap", "value": 1e9},
        ],
    },
    "high": {
        "label": "High risk (day-trade momentum)",
        "criteria": [
            {"key": "min_pct_change_today", "value": 10.0},
            {"key": "min_relative_volume", "value": 5.0},
            {"key": "min_price", "value": 2.0},
            {"key": "max_price", "value": 20.0},
            {"key": "max_float_shares", "value": 20_000_000},
            {"key": "min_gap_pct", "value": 2.0},
        ],
    },
}


def _fetch_raw_metrics(ticker: str) -> dict:
    if yf is None:
        raise RuntimeError("yfinance not installed. Run: pip install yfinance")
    t = yf.Ticker(ticker)
    info = t.info
    m = {
        "beta": info.get("beta"),
        "debtToEquity": info.get("debtToEquity"),
        "freeCashflow": info.get("freeCashflow"),
        "marketCap": info.get("marketCap"),
        "profitMargins": info.get("profitMargins"),
        "revenueGrowth": info.get("revenueGrowth"),
        "currentPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
        "previousClose": info.get("previousClose"),
        "regularMarketOpen": info.get("regularMarketOpen") or info.get("open"),
        "volume": info.get("volume") or info.get("regularMarketVolume"),
        "averageVolume": info.get("averageVolume") or info.get("averageDailyVolume10Day"),
        "floatShares": info.get("floatShares"),
    }
    price, prev_close = m["currentPrice"], m["previousClose"]
    m["pctChangeToday"] = ((price - prev_close) / prev_close * 100) if price and prev_close else None
    m["relativeVolume"] = (m["volume"] / m["averageVolume"]) if m["volume"] and m["averageVolume"] else None
    open_p = m["regularMarketOpen"]
    m["gapPct"] = ((open_p - prev_close) / prev_close * 100) if open_p and prev_close else None
    return m


@criterion("max_beta", "Beta \u2264 {value}", 0.8)
def max_beta(m, value):
    return None if m.get("beta") is None else m["beta"] <= value


@criterion("min_beta", "Beta \u2265 {value}", 1.0)
def min_beta(m, value):
    return None if m.get("beta") is None else m["beta"] >= value


@criterion("max_debt_equity", "Debt/Equity \u2264 {value}", 100)
def max_debt_equity(m, value):
    return None if m.get("debtToEquity") is None else m["debtToEquity"] <= value


@criterion("min_market_cap", "Market cap \u2265 ${value:,.0f}", 10e9)
def min_market_cap(m, value):
    return None if m.get("marketCap") is None else m["marketCap"] >= value


@criterion("positive_fcf", "Positive free cash flow", True)
def positive_fcf(m, value):
    if not value:
        return True
    return None if m.get("freeCashflow") is None else m["freeCashflow"] > 0


@criterion("positive_margin", "Positive profit margin", True)
def positive_margin(m, value):
    if not value:
        return True
    return None if m.get("profitMargins") is None else m["profitMargins"] > 0


@criterion("min_revenue_growth", "Revenue growth \u2265 {value:.0%} YoY", 0.15)
def min_revenue_growth(m, value):
    return None if m.get("revenueGrowth") is None else m["revenueGrowth"] >= value


@criterion("min_pct_change_today", "Already up \u2265 {value}% today", 10.0)
def min_pct_change_today(m, value):
    return None if m.get("pctChangeToday") is None else m["pctChangeToday"] >= value


@criterion("min_relative_volume", "Relative volume \u2265 {value}x average", 5.0)
def min_relative_volume(m, value):
    return None if m.get("relativeVolume") is None else m["relativeVolume"] >= value


@criterion("min_price", "Price \u2265 ${value}", 2.0)
def min_price(m, value):
    return None if m.get("currentPrice") is None else m["currentPrice"] >= value


@criterion("max_price", "Price \u2264 ${value}", 20.0)
def max_price(m, value):
    return None if m.get("currentPrice") is None else m["currentPrice"] <= value


@criterion("max_float_shares", "Float \u2264 {value:,.0f} shares", 20_000_000)
def max_float_shares(m, value):
    return None if m.get("floatShares") is None else m["floatShares"] <= value


@criterion("min_gap_pct", "Gapped up \u2265 {value}% at open", 2.0)
def min_gap_pct(m, value):
    return None if m.get("gapPct") is None else m["gapPct"] >= value


def evaluate_ticker_custom(ticker: str, criteria_list: list) -> dict:
    """
    criteria_list: [{"key": "max_beta", "value": 0.8}, ...]
    Returns {ticker, criteria: [{key, label, passed}], passed_count, total_count}
    """
    metrics = _fetch_raw_metrics(ticker)
    results = []
    for c in criteria_list:
        key, value = c["key"], c["value"]
        if key not in CRITERIA_REGISTRY:
            continue
        spec = CRITERIA_REGISTRY[key]
        try:
            passed = spec["func"](metrics, value)
        except Exception:
            passed = None
        try:
            label = spec["label_template"].format(value=value)
        except Exception:
            label = spec["label_template"]
        results.append({"key": key, "label": label, "passed": passed})

    countable = [r for r in results if r["passed"] is not None]
    passed_count = sum(1 for r in countable if r["passed"])

    return {
        "ticker": ticker,
        "criteria": results,
        "passed_count": passed_count,
        "total_count": len(countable),
        "raw_metrics": metrics,
    }


def evaluate_ticker(ticker: str, profile: str = "low", overrides: dict = None) -> dict:
    """Preset-based evaluation. profile: "low" | "medium" | "high".
    overrides: {criterion_key: new_value} to override specific preset defaults."""
    preset = PRESETS[profile]
    criteria_list = [
        {"key": c["key"], "value": (overrides or {}).get(c["key"], c["value"])}
        for c in preset["criteria"]
    ]
    result = evaluate_ticker_custom(ticker, criteria_list)
    result["profile"] = profile
    return result


def evaluate_multiple(tickers: list, profile: str = "low", overrides: dict = None) -> list:
    return [evaluate_ticker(t, profile, overrides) for t in tickers]


def evaluate_multiple_custom(tickers: list, criteria_list: list) -> list:
    return [evaluate_ticker_custom(t, criteria_list) for t in tickers]
