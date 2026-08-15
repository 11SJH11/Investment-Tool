"""
macro.py

Pulls headline macro indicators from FRED (Federal Reserve Economic Data) --
a free, official US government source. Requires a free API key from
https://fred.stlouisfed.org/docs/api/api_key.html

This is context only -- it never produces a score or a buy/sell signal.
It's meant to sit next to your other numbers so you can factor in the
economic backdrop yourself, the way an analyst would.
"""

import os
import requests

FRED_API_KEY = os.environ.get("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series IDs for the indicators we care about
SERIES = {
    "fed_funds_rate": {"id": "FEDFUNDS", "label": "Fed Funds Rate", "unit": "%"},
    "cpi_yoy": {"id": "CPIAUCSL", "label": "CPI (Inflation)", "unit": "index", "yoy": True},
    "unemployment_rate": {"id": "UNRATE", "label": "Unemployment Rate", "unit": "%"},
    "treasury_10y": {"id": "DGS10", "label": "10-Year Treasury Yield", "unit": "%"},
}


def _fetch_series(series_id: str, limit: int = 14):
    """Fetches the most recent observations for one FRED series."""
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    observations = [o for o in data.get("observations", []) if o["value"] != "."]
    return observations


def get_macro_snapshot() -> dict:
    """
    Returns current values (and recent trend direction) for each headline
    indicator. Raises a clear error if no API key is configured.
    """
    if not FRED_API_KEY:
        raise RuntimeError(
            "No FRED_API_KEY configured. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html and set it "
            "as an environment variable."
        )

    result = {}
    for key, meta in SERIES.items():
        try:
            obs = _fetch_series(meta["id"])
            if not obs:
                continue

            if meta.get("yoy"):
                # CPI needs year-over-year % change, not the raw index value
                latest = float(obs[0]["value"])
                year_ago = next((float(o["value"]) for o in obs if o["date"] <= _one_year_before(obs[0]["date"])), None)
                if year_ago:
                    value = (latest - year_ago) / year_ago * 100
                else:
                    value = None
                trend = None
            else:
                value = float(obs[0]["value"])
                prior = float(obs[1]["value"]) if len(obs) > 1 else value
                trend = "rising" if value > prior else ("falling" if value < prior else "flat")

            result[key] = {
                "label": meta["label"],
                "value": round(value, 2) if value is not None else None,
                "unit": "%" if meta.get("yoy") else meta["unit"],
                "trend": trend,
                "as_of": obs[0]["date"],
            }
        except Exception as e:
            result[key] = {"label": meta["label"], "error": str(e)}

    return result


def _one_year_before(date_str: str) -> str:
    y, m, d = date_str.split("-")
    return f"{int(y) - 1}-{m}-{d}"
