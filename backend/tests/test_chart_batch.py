from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
import pytest
from fastapi import HTTPException
from app.api.research import chart_batch, ChartBatchRequest
from app.data.instruments import instrument_spec

class Market:
    def __init__(self): self.calls=[]
    def instrument_info(self,ticker):return instrument_spec(ticker)
    def provider_for(self,ticker):return SimpleNamespace(key='fixture')
    def historical_delay_minutes(self,ticker):return 0
    def latest_available_end(self,ticker,timeframe,end):return end
    def get_bars(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        return pd.DataFrame({'timestamp':pd.date_range('2026-09-01T14:00:00Z',periods=50,freq='min'),'open':range(50),'high':range(1,51),'low':range(50),'close':range(1,51),'volume':[10]*50})

def test_chart_batch_prepares_once_and_matches_individual_indicators():
    from app.services.chart_data import prepare_chart_bars
    market=Market();services=SimpleNamespace(market_data=market)
    with patch('app.api.research.prepare_chart_bars', wraps=prepare_chart_bars) as prepare:
        result=chart_batch('AAPL',ChartBatchRequest(timeframe='1m',refresh=True,indicators=[{'key':'ema','params':{'length':20}},{'key':'ema','params':{'length':50}}]),services)
    assert len(market.calls)==1 and prepare.call_count==1
    assert market.calls[0][1]['force_refresh'] is True
    from app.indicators import indicator_registry
    frame=pd.DataFrame(result['bars']);frame['timestamp']=pd.to_datetime(frame['timestamp'],utc=True)
    for item in result['indicators']:
        expected=indicator_registry.create(item['key']).calculate(frame,**item['params']).dropna()
        assert [p['value'] for p in item['values']]==pytest.approx(expected.tolist())
    assert result['provider']=='fixture' and result['count']==50

def test_unknown_batch_indicator_rejected_before_market_work():
    market=Market()
    with pytest.raises(HTTPException):chart_batch('AAPL',ChartBatchRequest(indicators=[{'key':'absent'}]),SimpleNamespace(market_data=market))
    assert market.calls==[]


def test_historical_handoff_caps_fetch_at_requested_end():
    from datetime import datetime, timezone
    market=Market();end=datetime(2026,1,5,20,tzinfo=timezone.utc)
    chart_batch('AAPL',ChartBatchRequest(timeframe='1m',end_at=end),SimpleNamespace(market_data=market))
    assert market.calls[0][0][3]==end


def test_cache_diagnostics_exposes_only_safe_coverage(tmp_path):
    from app.storage.database import Database
    from app.api.data import cache_diagnostics
    db=Database(tmp_path/'cache.db');db.initialize()
    db.set_setting('secret-fixture','not-for-response')
    with db.connect() as con:
        con.execute("INSERT INTO market_cache_coverage(namespace,ticker,timeframe,covered_start,covered_end) VALUES('alpaca-sip','AAPL','1m','2026-01-01','2026-01-02')")
    result=cache_diagnostics(SimpleNamespace(database=db))
    assert result['items'][0]['source_timeframe']=='1m'
    assert 'not-for-response' not in str(result) and 'secret-fixture' not in str(result)
