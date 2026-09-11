from __future__ import annotations

from app.data.providers.base import FundamentalsProvider
from app.storage.json_cache import JsonCacheRepository


class FundamentalsService:
    def __init__(self, provider: FundamentalsProvider, cache: JsonCacheRepository, ttl_seconds: int):
        self.provider = provider
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    def get(self, ticker: str, *, refresh: bool = False) -> dict:
        ticker = ticker.upper().strip()
        key = f"{self.provider.key}:{ticker}"
        if not refresh:
            cached = self.cache.get("fundamentals", key)
            if cached is not None:
                return cached
        result = self.provider.get_fundamentals(ticker)
        self.cache.set("fundamentals", key, result, self.ttl_seconds)
        return result
