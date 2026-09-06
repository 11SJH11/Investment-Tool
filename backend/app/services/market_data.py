from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.data.providers.base import MarketDataProvider, Timeframe
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore


class MarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider,
        store: MarketStore,
        coverage: MarketCacheRepository,
    ):
        self.provider = provider
        self.store = store
        self.coverage = coverage

    def get_bars(
        self,
        ticker: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        ticker = ticker.upper().strip()
        start = _utc(start)
        end = _utc(end)
        if start >= end:
            raise ValueError("start must be before end")

        namespace = self.provider.cache_namespace
        if force_refresh:
            self._fetch_and_store(ticker, timeframe, start, end)
        else:
            cached = self.coverage.get(namespace, ticker, timeframe)
            if cached is None:
                self._fetch_and_store(ticker, timeframe, start, end)
            else:
                cached_start, cached_end = cached
                if start < cached_start:
                    self._fetch_and_store(ticker, timeframe, start, cached_start)
                if end > cached_end:
                    self._fetch_and_store(ticker, timeframe, cached_end, end)

        return self.store.read_bars(namespace, ticker, timeframe, start=start, end=end)

    def _fetch_and_store(self, ticker: str, timeframe: Timeframe, start: datetime, end: datetime) -> None:
        if start >= end:
            return
        bars = self.provider.get_bars(ticker, timeframe, start, end)
        if not bars.empty:
            self.store.write_bars(self.provider.cache_namespace, ticker, timeframe, bars)
        # Mark requested coverage even when the market was closed/no bars were returned.
        self.coverage.extend(self.provider.cache_namespace, ticker, timeframe, start, end)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
