"""Verified broker Gold history for research, never a broker execution adapter."""
from threading import Lock
import math

import duckdb
import pandas as pd

from app.brokers.mt5_symbols import fingerprint
from app.core.safe_errors import ProviderConfigurationError, MissingHistoryError
from app.data.providers.base import MarketDataProvider
from app.storage.mt5_history_store import MT5HistoryStore


IDENTITY_FIELDS = ('name','currency_base','currency_profit','instrument_type',
                   'trade_contract_size','trade_tick_size','volume_min','volume_step',
                   'trade_calc_mode','chart_mode','expiration_time')


def gold_identity(row):
    return {k:row.get(k) for k in IDENTITY_FIELDS}


def eligible_gold(row):
    return (row.get('currency_base')=='XAU' and row.get('currency_profit')=='USD'
        and row.get('instrument_type') in {'forex','cfd'} and not row.get('custom')
        and row.get('expiration_time')==0 and row.get('chart_mode')==0
        and all(isinstance(row.get(k),(int,float)) and math.isfinite(row[k]) and row[k]>0
                for k in ('trade_contract_size','trade_tick_size','volume_min','volume_step')))


class MT5SpotMetalProvider(MarketDataProvider):
    key='mt5_spot_metal'
    historical_delay_minutes=0
    historical_feed='broker_native_bid_tick_volume'
    adjustment='unadjusted'

    def __init__(self, connections, profile_id, account_key, environment, metadata):
        if not eligible_gold(metadata):
            raise ProviderConfigurationError('MT5 Gold requires verified XAU/USD spot identity and bid-based chart metadata')
        self.connections=connections
        self.profile_id=profile_id
        self.account_key=account_key
        self.environment=environment
        self.identity=gold_identity(metadata)
        self.cache_namespace='mt5-gold-bid-v1-'+fingerprint([account_key,environment,self.identity])[:32]
        self.research_provenance=dict(provider=self.key,broker_symbol=self.identity['name'],
            account_key=account_key,environment=environment,instrument=self.identity,
            price_basis='bid',volume_semantics='tick_count_not_exchange_volume',
            quantity_basis='metal_units_not_broker_lots',broker_execution_parity=False,
            historical_specification_verified=False,coverage_complete=False,
            selection_reason='OANDA unavailable; one verified selected MT5 Gold source')

    def get_quote(self,ticker):
        raise MissingHistoryError('This MT5 Gold adapter supplies historical research bars, not live execution quotes')

    def get_bars(self,ticker,timeframe,start,end):
        if ticker not in {'XAUUSD','XAU_USD'} or timeframe not in {'1m','5m','15m','30m','1h','4h'}:
            raise MissingHistoryError('MT5 Gold research supports intraday XAUUSD bars only; broker daily sessions are not verified')
        status=self.connections.status(self.profile_id)
        if not status.get('configured') or status.get('disconnected') or status.get('account_key')!=self.account_key or status.get('environment')!=self.environment:
            raise ProviderConfigurationError('MT5 Gold account changed or disconnected; no source substitution permitted')
        start,end=pd.Timestamp(start),pd.Timestamp(end)
        if start.tzinfo is None or end.tzinfo is None or end<=start:
            raise ValueError('Gold history requires ordered timezone-aware dates')
        frames=[]
        store=MT5HistoryStore(self.connections.database)
        cursor=start
        while cursor<end:
            stop=min(end,cursor+pd.Timedelta(days=7))
            manifest=self.connections.market_history(self.profile_id,dict(
                symbol=self.identity['name'],data_type=timeframe,start=cursor,end=stop))
            if manifest['account_key']!=self.account_key or manifest['environment']!=self.environment or gold_identity(manifest['symbol_metadata'])!=self.identity:
                raise ProviderConfigurationError('MT5 Gold identity or contract specifications changed; start a separate dataset')
            path=store.root/(manifest['data_fingerprint']+'.parquet')
            if store.digest(path)!=manifest['data_fingerprint']:
                raise MissingHistoryError('MT5 Gold cache integrity verification failed')
            with duckdb.connect() as connection:
                frame=connection.execute('SELECT * FROM read_parquet(?)',[str(path)]).df()
            frames.append(frame)
            cursor=stop
        frame=pd.concat(frames,ignore_index=True).sort_values('timestamp').reset_index(drop=True)
        frame['volume']=frame['tick_volume']
        frame['provider']=self.key
        frame['broker_symbol']=self.identity['name']
        frame['price_basis']='bid'
        frame['volume_semantics']='tick_count_not_exchange_volume'
        return frame


class GoldDataRoute:
    """Prefer the established configured source; pin a verified alternative once.

    This is eligibility-based routing, not an unmeasured quality ranking. There is
    no fallback after provider errors and no opportunistic source mixing.
    """
    def __init__(self,oanda,connections):
        self.provider=oanda
        self.connections=connections
        self.lock=Lock()

    def resolve(self):
        with self.lock:
            if self.provider is not None:return self.provider
            candidates=[]
            for profile in self.connections.statuses()['items']:
                if profile['provider']!='mt5' or not profile.get('configured') or profile.get('disconnected') or not profile.get('account_key'):continue
                catalog=self.connections.symbol_catalog(profile['profile_id'],refresh=True,limit=500)
                if catalog['catalog_total']>500:
                    raise ProviderConfigurationError('MT5 Gold catalog exceeds automatic discovery limit; no incomplete candidate selection')
                candidates.extend((profile,row) for row in catalog['items'] if eligible_gold(row))
            if len(candidates)!=1:
                raise ProviderConfigurationError('Gold needs configured OANDA or exactly one verified selected MT5 XAU/USD spot source; test/select the MT5 account in Settings')
            p,row=candidates[0]
            self.provider=MT5SpotMetalProvider(self.connections,p['profile_id'],p['account_key'],p['environment'],row)
            return self.provider
