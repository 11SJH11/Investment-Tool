from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutochartistProvider:
    """Safe integration scaffold for future Autochartist research data.

    Autochartist access supplied inside a broker portal/MT4/MT5 plugin does not
    automatically grant a reusable developer API contract. Ledger therefore
    stores only the configuration shape and exposes a capability report. It does
    not scrape broker pages, reuse short-lived portal tokens, or make speculative
    API requests.
    """

    enabled: bool = False
    broker_id: str | None = None
    user: str | None = None
    account_type: str = "LIVE"
    secret_key: str | None = None

    key: str = "autochartist"

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.broker_id and self.user and self.secret_key)

    def capability_report(self) -> dict:
        missing = []
        if not self.enabled:
            missing.append("AUTOCHARTIST_ENABLED=true")
        if not self.broker_id:
            missing.append("AUTOCHARTIST_BROKER_ID")
        if not self.user:
            missing.append("AUTOCHARTIST_USER")
        if not self.secret_key:
            missing.append("AUTOCHARTIST_SECRET_KEY")

        return {
            "provider": self.key,
            "configured": self.configured,
            "status": "credentials_present_not_validated" if self.configured else "not_configured",
            "account_type": self.account_type,
            "missing": missing,
            "remote_probe_performed": False,
            "remote_probe_reason": (
                "Ledger intentionally does not guess or scrape Autochartist authentication. "
                "When an approved developer API contract/endpoint is supplied, implement the "
                "probe here and keep portal credentials out of logs and responses."
            ),
            "planned_capabilities": [
                "technical_analysis",
                "market_snapshots",
                "volatility_analysis",
                "news_sentiment",
                "economic_calendar",
                "performance_statistics",
            ],
        }

    def fetch_items(self, *_, **__):
        raise RuntimeError(
            "Autochartist data access is scaffolded but not enabled. Supply an approved "
            "developer API contract before implementing network requests; do not scrape the portal."
        )
