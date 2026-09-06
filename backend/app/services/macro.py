from __future__ import annotations

from app.data.providers.base import MacroDataProvider
from app.storage.json_cache import JsonCacheRepository


class MacroService:
    def __init__(self, provider: MacroDataProvider, cache: JsonCacheRepository, ttl_seconds: int):
        self.provider = provider
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    def get_snapshot(self, *, refresh: bool = False) -> dict:
        key = self.provider.key
        if not refresh:
            cached = self.cache.get("macro", key)
            if cached is not None:
                return cached
        result = self.provider.get_snapshot()
        self.cache.set("macro", key, result, self.ttl_seconds)
        return result
