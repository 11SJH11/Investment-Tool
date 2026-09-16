"""Backend-only configuration. Public responses never serialize these objects."""
from dataclasses import dataclass, field
import json
import re

from app.brokers.base import BrokerHistoryError


@dataclass(repr=False)
class BrokerProfile:
    id: str
    provider: str
    environment: str
    enabled: bool = True
    credentials: dict = field(default_factory=dict, repr=False)

    @property
    def configured(self):
        required = {"oanda": ("token", "account_id"), "trading212": ("api_key", "api_secret"),
                    "tradovate": ("client_id", "client_secret", "account_id")}[self.provider]
        environments = {"practice", "live"} if self.provider == "oanda" else {"demo", "live"}
        return self.enabled and self.environment in environments and all(self.credentials.get(k, "").strip() for k in required)


def profiles(settings):
    result = [
        BrokerProfile("oanda-default", "oanda", settings.oanda_environment.strip().lower(), True,
                      {"token": settings.oanda_access_token or "", "account_id": settings.oanda_account_id or ""}),
        BrokerProfile("trading212-default", "trading212", settings.trading212_environment.strip().lower(), settings.trading212_enabled,
                      {"api_key": settings.trading212_api_key, "api_secret": settings.trading212_api_secret}),
        BrokerProfile("tradovate-default", "tradovate", settings.tradovate_environment.strip().lower(), settings.tradovate_enabled,
                      {"client_id": settings.tradovate_client_id, "client_secret": settings.tradovate_client_secret, "account_id": settings.tradovate_account_id}),
    ]
    try:
        extra = json.loads(settings.broker_profiles_json)
        if not isinstance(extra, list):
            raise ValueError()
        ids = {p.id for p in result}
        for item in extra:
            if not isinstance(item, dict) or set(item) - {"id", "provider", "environment", "enabled", "credentials"}:
                raise ValueError()
            profile = BrokerProfile(**item)
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,59}", profile.id) or profile.id in ids:
                raise ValueError()
            if profile.provider not in {"oanda", "trading212", "tradovate"} or not isinstance(profile.enabled, bool):
                raise ValueError()
            if not isinstance(profile.credentials, dict) or not all(isinstance(v, str) for v in profile.credentials.values()):
                raise ValueError()
            if not isinstance(profile.environment, str):
                raise ValueError()
            profile.environment = profile.environment.strip().lower()
            # Reject invalid environments instead of accidentally choosing a live host.
            if profile.environment not in ({"practice", "live"} if profile.provider == "oanda" else {"demo", "live"}):
                raise ValueError()
            ids.add(profile.id); result.append(profile)
    except Exception:
        raise BrokerHistoryError("Invalid BROKER_PROFILES_JSON; check unique profile IDs, provider, environment and credential fields") from None
    return result
