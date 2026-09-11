from __future__ import annotations

from datetime import datetime, timezone

from app.data.providers.fred import FredProvider


class FxRateService:
    """Small Phase 4.1 FX resolver.

    Ledger v2 is US-equities-first, so the first supported conversion is GBP<->USD.
    FRED DEXUSUK is USD per GBP. The interface is intentionally isolated so a broader
    FX provider can replace this without changing Portfolio logic later.
    """

    def __init__(self, fred: FredProvider | None):
        self.fred = fred

    def rate(self, from_currency: str, to_currency: str, at: datetime) -> dict:
        source = from_currency.upper()
        target = to_currency.upper()
        if source == target:
            return {"rate": 1.0, "source": "identity", "date": at.date().isoformat()}
        if {source, target} != {"GBP", "USD"}:
            raise ValueError(f"Phase 4.1 FX currently supports GBP/USD only, not {source}/{target}")
        if self.fred is None:
            raise ValueError("FRED is not configured, so Ledger cannot resolve historical GBP/USD automatically")

        obs = self.fred.get_observation_on_or_before("DEXUSUK", at.date().isoformat())
        if obs is None:
            raise ValueError(f"No GBP/USD observation available on or before {at.date().isoformat()}")
        usd_per_gbp = float(obs["value"])
        if usd_per_gbp <= 0:
            raise ValueError("Invalid GBP/USD rate returned by FRED")
        rate = usd_per_gbp if source == "GBP" else 1.0 / usd_per_gbp
        return {"rate": rate, "source": "fred:DEXUSUK", "date": obs["date"]}

    def latest(self, from_currency: str, to_currency: str) -> dict:
        return self.rate(from_currency, to_currency, datetime.now(timezone.utc))
