from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from app.data.instruments import InstrumentSpec, instrument_spec, normalize_symbol
from app.data.providers.base import MarketDataProvider, Timeframe
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore


ProviderResolver = Callable[[str, InstrumentSpec], MarketDataProvider]


class MarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider | None,
        store: MarketStore,
        coverage: MarketCacheRepository,
        *,
        provider_resolver: ProviderResolver | None = None,
    ):
        # ``provider`` remains the default/legacy provider (normally Alpaca) so
        # existing integrations/tests can continue to inspect it. Actual requests
        # route through provider_for().
        self.provider = provider
        self.store = store
        self.coverage = coverage
        self.provider_resolver = provider_resolver

    def instrument_info(self, ticker: str) -> InstrumentSpec:
        return instrument_spec(ticker)

    def provider_for(self, ticker: str) -> MarketDataProvider:
        symbol = normalize_symbol(ticker)
        spec = instrument_spec(symbol)
        if self.provider_resolver is not None:
            return self.provider_resolver(symbol, spec)
        if self.provider is None:
            raise RuntimeError(f"No market-data provider configured for {symbol}")
        return self.provider

    def historical_delay_minutes(self, ticker: str) -> int:
        return max(0, int(getattr(self.provider_for(ticker), "historical_delay_minutes", 0)))

    def latest_available_end(self, ticker: str, timeframe: Timeframe, reference: datetime | None = None) -> datetime:
        """Clamp a requested end to the provider's newest complete candle when supported."""
        provider = self.provider_for(ticker)
        reference = _utc(reference or datetime.now(timezone.utc))
        resolver = getattr(provider, "latest_available_end", None)
        if callable(resolver):
            try:
                return min(reference, _utc(resolver(ticker, timeframe, reference)))
            except Exception:
                # Do not make charting less reliable because an optional freshness probe
                # failed. The main data request still has its normal error handling.
                return reference
        return reference

    def get_bars(
        self,
        ticker: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        *,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        ticker = normalize_symbol(ticker)
        start = _utc(start)
        end = _utc(end)
        if start >= end:
            raise ValueError("start must be before end")

        provider = self.provider_for(ticker)
        # Backward adjustment depends on later rolls in the requested range.
        spec = instrument_spec(ticker)
        if force_refresh and spec.security_type == "continuous_future" and hasattr(provider, "list_contracts"):
            provider.list_contracts(spec.root, refresh=True)
        if spec.security_type == 'continuous_future' and hasattr(provider,'raw_execution_provider'):
            from copy import copy
            continuous = copy(provider)
            continuous.refresh_schedule = force_refresh
            raw = MarketDataService(provider.raw_execution_provider(),self.store,self.coverage)
            continuous.contract_loader = lambda symbol,tf,a,b: raw.get_bars(symbol,tf,a,b,force_refresh=force_refresh)
            # Cache dated OHLCV, then restitch against the current versioned
            # schedule. Never leave an old contract in cached alias history when
            # delayed provider roll evidence becomes available.
            return continuous.get_bars(ticker,timeframe,start,end)
        # Never merge independently adjusted segments into a shared cache.
        if instrument_spec(ticker).security_type == "continuous_future" and getattr(provider, "back_adjust", False):
            return provider.get_bars(ticker, timeframe, start, end)
        namespace = provider.cache_namespace
        if force_refresh:
            self._fetch_and_store(provider, ticker, timeframe, start, end)
        else:
            cached = self.coverage.get(namespace, ticker, timeframe)
            if cached is None:
                self._fetch_and_store(provider, ticker, timeframe, start, end)
            else:
                cached_start, cached_end = cached
                if start < cached_start:
                    self._fetch_and_store(provider, ticker, timeframe, start, cached_start)
                if end > cached_end:
                    self._fetch_and_store(provider, ticker, timeframe, cached_end, end)

        return self.store.read_bars(namespace, ticker, timeframe, start=start, end=end)

    def get_execution_bars(self, ticker, timeframe, start, end):
        provider = self.provider_for(ticker)
        if hasattr(provider, 'raw_execution_provider'):
            raw = provider.raw_execution_provider()
            return MarketDataService(raw,self.store,self.coverage).get_bars(ticker,timeframe,start,end)
        return self.get_bars(ticker,timeframe,start,end)

    def _fetch_and_store(
        self,
        provider: MarketDataProvider,
        ticker: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> None:
        if start >= end:
            return
        bars = provider.get_bars(ticker, timeframe, start, end)
        if not bars.empty:
            self.store.write_bars(provider.cache_namespace, ticker, timeframe, bars)
        # Mark requested coverage even when the market was closed/no bars were returned.
        self.coverage.extend(provider.cache_namespace, ticker, timeframe, start, end)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
