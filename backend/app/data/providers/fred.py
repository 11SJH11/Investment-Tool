from __future__ import annotations

from typing import Any

from app.data.http import JsonHttpClient
from app.data.providers.base import MacroDataProvider


class FredProvider(MacroDataProvider):
    key = "fred"

    SERIES = {
        "fed_funds_rate": {"series_id": "FEDFUNDS", "label": "Federal funds rate", "units": None},
        "treasury_10y": {"series_id": "DGS10", "label": "10-year Treasury yield", "units": None},
        "unemployment_rate": {"series_id": "UNRATE", "label": "Unemployment rate", "units": None},
        "cpi_yoy": {"series_id": "CPIAUCSL", "label": "CPI year-over-year", "units": "pc1"},
    }

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.stlouisfed.org",
        http: JsonHttpClient | None = None,
    ):
        if not api_key:
            raise ValueError("FRED API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http = http or JsonHttpClient()

    def get_series(self, series_id: str, *, units: str | None = None, limit: int = 24) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": limit,
        }
        if units:
            params["units"] = units
        payload = self.http.get_json(
            f"{self.base_url}/fred/series/observations",
            params=params,
        )
        observations: list[dict[str, Any]] = []
        for item in payload.get("observations") or []:
            value = item.get("value")
            if value in (None, "."):
                continue
            observations.append({"date": item.get("date"), "value": float(value)})
        return observations


    def get_observation_on_or_before(self, series_id: str, date_value: str) -> dict[str, Any] | None:
        """Return the latest non-missing observation on or before YYYY-MM-DD."""
        params: dict[str, Any] = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,
            "observation_end": date_value,
        }
        payload = self.http.get_json(
            f"{self.base_url}/fred/series/observations",
            params=params,
        )
        for item in payload.get("observations") or []:
            value = item.get("value")
            if value not in (None, "."):
                return {"date": item.get("date"), "value": float(value)}
        return None

    def get_snapshot(self) -> dict:
        result: dict[str, Any] = {}
        for key, spec in self.SERIES.items():
            observations = self.get_series(spec["series_id"], units=spec["units"], limit=12)
            latest = observations[0] if observations else None
            previous = observations[1] if len(observations) > 1 else None
            trend = None
            if latest and previous:
                if latest["value"] > previous["value"]:
                    trend = "rising"
                elif latest["value"] < previous["value"]:
                    trend = "falling"
                else:
                    trend = "flat"
            result[key] = {
                "series_id": spec["series_id"],
                "label": spec["label"],
                "value": latest["value"] if latest else None,
                "date": latest["date"] if latest else None,
                "trend": trend,
                "unit": "%",
            }
        return result
