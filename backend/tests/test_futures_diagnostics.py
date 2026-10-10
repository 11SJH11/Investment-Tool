from types import SimpleNamespace as NS
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.data import router
from app.data.providers.registry import ProviderRegistry
from app.services.futures_diagnostics import diagnose, compare_frames
from app.data.instruments import instrument_spec
from app.services.market_data import MarketDataService
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.database import Database
from tests.test_mt5_market_data import provider, Terminal, START, END

def test_comparison_reports_differences_and_timestamp_coverage():
    p=provider(Terminal());a=p.get_bars('NQH25','1m',START,END);b=a.iloc[1:].copy();b['close']+=.25;b['volume']+=1;b['source_contract']='NQM25'
    result=compare_frames(a,b)
    assert result['common_timestamps']==2 and result['only_massive']==1 and result['only_mt5']==0
    assert result['contract_mismatch_bars']==2
    assert result['differences']['close']['mean_absolute_difference']==.25
    assert result['differences']['volume']['different']==2

def test_diagnostics_api_uses_cache_and_never_changes_provider(tmp_path):
    mt=Terminal();p=provider(mt);db=Database(tmp_path/'db');db.initialize();registry=ProviderRegistry();registry.register('market_data_mt5',p)
    market=MarketDataService(p,MarketStore(tmp_path/'bars'),MarketCacheRepository(db))
    services=NS(providers=registry,market_data=market)
    app=FastAPI();app.state.services=services;app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        result=client.post('/api/data/futures/diagnostics',json={'symbol':'NQH25','timeframe':'1m','start':START.isoformat(),'end':END.isoformat()}).json()
    assert result['providers']['mt5']['bars']==3 and len(mt.calls)==1
    assert result['providers']['massive']['status']=='unavailable'
    assert market.provider is p
    with pytest.raises(ValueError):diagnose(services,'NAS100','1m',START,END)
    with pytest.raises(ValueError):diagnose(services,'NQ1!','1m',START,END+pd.Timedelta(days=32))

def test_gold_futures_and_cfd_instruments_remain_distinct():
    assert instrument_spec('XAUUSD').provider_key=='oanda'
    assert instrument_spec('GC').root=='GC' and instrument_spec('GC').asset_type=='future'
    for symbol in ['NAS100','US100','USTEC']:
        assert instrument_spec(symbol).asset_type=='cfd' and instrument_spec(symbol).root is None
    assert instrument_spec('NQ').root=='NQ' and instrument_spec('MNQ').root=='MNQ'
