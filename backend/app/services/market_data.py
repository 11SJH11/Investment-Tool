from __future__ import annotations
from app.performance import timed, profiled, measure


from datetime import datetime, timezone, timedelta
from typing import Callable
from threading import RLock
from collections import defaultdict

import pandas as pd

from app.data.instruments import InstrumentSpec, instrument_spec, normalize_symbol
from app.data.providers.base import MarketDataProvider, Timeframe
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore


ProviderResolver = Callable[[str, InstrumentSpec], MarketDataProvider]
_PROVIDER_LOCKS = defaultdict(RLock)
_LOCK_GUARD = RLock()


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
                with self._provider_lock(provider):
                    return min(reference, _utc(resolver(ticker, timeframe, reference)))
            except Exception:
                # Do not make charting less reliable because an optional freshness probe
                # failed. The main data request still has its normal error handling.
                return reference
        return reference

    def get_bars(
        self, ticker, timeframe, start, end, *, force_refresh=False,
    ):
        provider = self.provider_for(ticker)
        # Shared across service copies (including continuous -> dated contracts).
        # RLock makes that recursion safe; coverage is rechecked after waiting.
        with self._provider_lock(provider):
            return self._get_bars(ticker, timeframe, start, end, force_refresh=force_refresh)

    def _provider_lock(self, provider):
        with _LOCK_GUARD:
            root = getattr(self.store, 'root', None)
            return _PROVIDER_LOCKS[(str(root.resolve()) if root is not None else id(self.store), getattr(provider, 'key', type(provider).__name__))]

    def _get_bars(
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
        if force_refresh:
            from app.frame_cache import frames
            frames.clear()
        spec = instrument_spec(ticker)
        if spec.security_type == 'continuous_future' and hasattr(provider,'raw_execution_provider'):
            return self._continuous_bars(provider, ticker, timeframe, start, end, force_refresh=force_refresh)
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

    def _continuous_bars(self, provider, ticker, timeframe, start, end, *, force_refresh=False):
        """Reconstruct a continuous alias from durable dated contracts.

        A derived Parquet snapshot is persisted for fast replay/backtests, but it
        is accepted only while the source contract files/reference cache still
        match the manifest and the manifest was validated recently.  Dated raw
        contract Parquet remains the authoritative cache/provenance.
        """
        from copy import copy
        continuous = copy(provider)
        continuous.refresh_schedule = force_refresh
        raw_provider = provider.raw_execution_provider()
        raw = MarketDataService(raw_provider, self.store, self.coverage)
        continuous.contract_loader = lambda symbol,tf,a,b: raw.get_bars(symbol,tf,a,b,force_refresh=force_refresh)
        def source_identity(symbol, tf, a, b):
            namespace = raw.provider.cache_namespace
            covered = self.coverage.get(namespace, symbol, tf)
            if covered is None or covered[0] > a or covered[1] < b:
                return None
            path = self.store._path(namespace, symbol, tf)
            if not path.exists():
                return None
            stat = path.stat()
            return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        continuous.source_identity = source_identity

        derived_namespace = f"derived-continuous-v1-{provider.cache_namespace}"
        manifest = self.store.read_metadata('continuous', derived_namespace, ticker, timeframe)
        now = datetime.now(timezone.utc)
        if not force_refresh and self._continuous_manifest_valid(manifest, provider, raw_provider, ticker, timeframe, start, end, now):
            cached = self.store.read_bars(derived_namespace, ticker, timeframe, start=start, end=end)
            if not cached.empty:
                return cached

        union_start, union_end = start, end
        if manifest:
            try:
                union_start = min(start, _utc(datetime.fromisoformat(manifest['covered_start'])))
                union_end = max(end, _utc(datetime.fromisoformat(manifest['covered_end'])))
            except (KeyError, ValueError, TypeError):
                pass
        # The reconstruction itself loads only missing dated-contract ranges via
        # the normal persistent MarketDataService cache.
        result = continuous.get_bars(ticker, timeframe, union_start, union_end)
        if not result.empty:
            self.store.replace_bars(derived_namespace, ticker, timeframe, result)
            sources = {}
            if 'source_contract' in result.columns:
                for contract in sorted(set(str(v) for v in result.source_contract.dropna() if str(v))):
                    path = self.store._path(raw_provider.cache_namespace, contract, timeframe)
                    if path.exists():
                        stat = path.stat(); sources[contract] = [str(path.resolve()), stat.st_mtime_ns, stat.st_size]
            reference_path = getattr(getattr(provider, 'reference_cache', None), 'path', None)
            reference_identity = None
            if reference_path and reference_path.exists():
                stat=reference_path.stat(); reference_identity=[str(reference_path.resolve()),stat.st_mtime_ns,stat.st_size]
            self.store.write_metadata('continuous', derived_namespace, ticker, timeframe, {
                'version':'continuous-derived-v1','ticker':ticker,'timeframe':timeframe,
                'provider_namespace':provider.cache_namespace,'raw_namespace':raw_provider.cache_namespace,
                'roll_policy':getattr(provider,'roll_policy',None),'adjustment':getattr(provider,'adjustment',None),
                'covered_start':union_start.isoformat(),'covered_end':union_end.isoformat(),
                'validated_at':now.isoformat(),'sources':sources,'reference_identity':reference_identity,
            })
        stamps = pd.to_datetime(result.timestamp, utc=True) if not result.empty else pd.Series([],dtype='datetime64[ns, UTC]')
        return result.loc[(stamps>=pd.Timestamp(start))&(stamps<=pd.Timestamp(end))].reset_index(drop=True) if not result.empty else result

    def _continuous_manifest_valid(self, manifest, provider, raw_provider, ticker, timeframe, start, end, now):
        if not manifest or manifest.get('version') != 'continuous-derived-v1':
            return False
        if manifest.get('provider_namespace') != provider.cache_namespace or manifest.get('raw_namespace') != raw_provider.cache_namespace:
            return False
        if manifest.get('roll_policy') != getattr(provider,'roll_policy',None) or manifest.get('adjustment') != getattr(provider,'adjustment',None):
            return False
        try:
            covered_start=_utc(datetime.fromisoformat(manifest['covered_start']));covered_end=_utc(datetime.fromisoformat(manifest['covered_end']))
            validated=_utc(datetime.fromisoformat(manifest['validated_at']))
        except (KeyError,ValueError,TypeError):
            return False
        # A fully covered historical snapshot stays valid across restarts until an
        # authoritative source-contract/reference fingerprint changes.  New tail
        # requests naturally miss covered_end and rebuild only the extended union;
        # force_refresh also bypasses this path.  Avoid a wall-clock TTL here: it
        # made NQ1! reconstruct months of already-cached history every few hours.
        if covered_start>start or covered_end<end:
            return False
        path=self.store._path(f"derived-continuous-v1-{provider.cache_namespace}",ticker,timeframe)
        if not path.exists():
            return False
        for contract,identity in (manifest.get('sources') or {}).items():
            source=self.store._path(raw_provider.cache_namespace,contract,timeframe)
            if not source.exists(): return False
            stat=source.stat()
            if [str(source.resolve()),stat.st_mtime_ns,stat.st_size] != identity: return False
        reference_path=getattr(getattr(provider,'reference_cache',None),'path',None)
        recorded=manifest.get('reference_identity')
        if recorded:
            if not reference_path or not reference_path.exists(): return False
            stat=reference_path.stat()
            if [str(reference_path.resolve()),stat.st_mtime_ns,stat.st_size] != recorded: return False
        return True

    def continuous_cache_status(self, ticker: str, timeframe: Timeframe = '1m') -> dict | None:
        """Safe diagnostic summary for a persisted continuous-futures snapshot."""
        ticker = normalize_symbol(ticker)
        if instrument_spec(ticker).security_type != 'continuous_future':
            return None
        provider = self.provider_for(ticker)
        if not hasattr(provider, 'raw_execution_provider'):
            return None
        namespace = f"derived-continuous-v1-{provider.cache_namespace}"
        manifest = self.store.read_metadata('continuous', namespace, ticker, timeframe)
        if not manifest:
            return None
        sources = sorted((manifest.get('sources') or {}).keys())
        return {
            'ticker': ticker,
            'timeframe': timeframe,
            'covered_start': manifest.get('covered_start'),
            'covered_end': manifest.get('covered_end'),
            'validated_at': manifest.get('validated_at'),
            'provider_cache': manifest.get('provider_namespace'),
            'raw_provider_cache': manifest.get('raw_namespace'),
            'roll_policy': manifest.get('roll_policy'),
            'adjustment': manifest.get('adjustment'),
            'source_contract_count': len(sources),
            'source_contracts': sources,
            'status': 'ready' if self.store._path(namespace, ticker, timeframe).exists() else 'metadata_only',
        }

    def continuous_cache_entries(self) -> list[dict]:
        entries=[]
        for manifest in self.store.list_metadata('continuous'):
            ticker=manifest.get('ticker'); timeframe=manifest.get('timeframe')
            if not ticker or not timeframe:
                continue
            try:
                status=self.continuous_cache_status(str(ticker), str(timeframe))
            except Exception:
                status=None
            if status:
                entries.append(status)
        entries.sort(key=lambda row: (str(row.get('ticker')), str(row.get('timeframe'))))
        return entries

    def get_execution_bars(self, ticker, timeframe, start, end):
        provider = self.provider_for(ticker)
        if hasattr(provider, 'raw_execution_provider'):
            raw = provider.raw_execution_provider()
            return MarketDataService(raw,self.store,self.coverage).get_bars(ticker,timeframe,start,end)
        return self.get_bars(ticker,timeframe,start,end)

    @timed('fetch_and_store')
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
        with measure('provider_fetch'):
            bars = provider.get_bars(ticker, timeframe, start, end)
        if not bars.empty:
            self.store.write_bars(provider.cache_namespace, ticker, timeframe, bars)
        # Mark requested coverage even when the market was closed/no bars were returned.
        self.coverage.extend(provider.cache_namespace, ticker, timeframe, start, end)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
