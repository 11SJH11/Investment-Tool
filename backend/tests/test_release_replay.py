from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.strategy_lab import router
from app.services.backtest import BacktestService


class Market:
    def __init__(self):
        self.frame = pd.DataFrame([
            dict(timestamp=t,open=100+i,high=102+i,low=99+i,close=101+i,volume=10+i)
            for i,t in enumerate(pd.date_range('2026-06-02T13:30:00Z',periods=90,freq='min'))
        ])
        self.calls = []
    def get_bars(self, symbol, timeframe, start, end):
        self.calls.append(timeframe)
        return self.frame.loc[(self.frame.timestamp>=pd.Timestamp(start))&(self.frame.timestamp<pd.Timestamp(end))].copy()


def replay(market=None, timeframe='5m', frontier=None, **kwargs):
    return BacktestService(market or Market()).replay_bars(symbol='AAPL',timeframe=timeframe,
        session='regular',replay_date=pd.Timestamp('2026-06-02').date(),start_time='10:02',
        context_bars=10,frontier=frontier,**kwargs)


@pytest.mark.parametrize('tf',['5m','15m','30m','1h','4h'])
def test_partial_higher_timeframe_has_no_unrevealed_prices_or_volume(tf):
    market = Market()
    result = replay(market,tf)
    frontier = pd.Timestamp('2026-06-02T14:02:00Z')
    last = result['bars'][-1]
    known = market.frame.loc[(market.frame.timestamp>=pd.Timestamp(last['timestamp']))&(market.frame.timestamp<=frontier)]
    assert last['open'] == known.open.iloc[0]
    assert last['close'] == known.close.iloc[-1]
    assert last['high'] == known.high.max()
    assert last['low'] == known.low.min()
    assert last['volume'] == known.volume.sum()
    assert last['is_partial'] is True
    assert all(pd.Timestamp(b['timestamp'])<=frontier for b in result['source_bars'])
    assert all(isinstance(t,str) for t in result['timeline'])
    assert set(market.calls)=={'1m'}


def test_exact_boundary_then_rewind_and_timeframe_roundtrip():
    for minute,partial in [(4,False),(5,True)]:
        r=replay(frontier=pd.Timestamp(f'2026-06-02T14:0{minute}:00Z'))
        assert r['bars'][-1]['is_partial'] is partial
    before=replay(timeframe='1m')
    advanced=replay(timeframe='15m',frontier=pd.Timestamp('2026-06-02T14:14:00Z'))
    rewound=replay(timeframe='5m',frontier=pd.Timestamp(before['frontier']))
    back=replay(timeframe='1m',frontier=pd.Timestamp(rewound['frontier']))
    assert back['bars']==before['bars']
    assert pd.Timestamp(advanced['frontier'])>pd.Timestamp(back['frontier'])


@pytest.mark.parametrize('key,params',[('volume',{}),('ema',{'length':2}),('vwap',{})])
def test_future_mutation_cannot_change_indicator_or_partial_candle(key,params):
    m=Market(); service=BacktestService(m)
    args=dict(symbol='AAPL',timeframe='5m',session='regular',replay_date=pd.Timestamp('2026-06-02').date(),start_time='10:02',context_bars=10,key=key,params=params)
    original=service.replay_indicator(**args)
    bars=replay(m)['bars']
    m.frame.loc[m.frame.timestamp>pd.Timestamp('2026-06-02T14:02:00Z'),['high','close','volume']]=1e9
    assert service.replay_indicator(**args)==original
    assert replay(m)['bars']==bars
    assert max(pd.Timestamp(v['timestamp']) for v in original['values'])<=pd.Timestamp('2026-06-02T14:02:00Z')


def test_xau_24h_uses_revealed_minutes_outside_equity_hours():
    m=Market();m.frame['timestamp']=pd.date_range('2026-06-02T00:00:00Z',periods=90,freq='min')
    r=BacktestService(m).replay_bars(symbol='XAUUSD',timeframe='15m',session='24h',replay_date=pd.Timestamp('2026-06-01').date(),replay_end_date=pd.Timestamp('2026-06-02').date(),start_time='20:02',context_bars=0)
    assert r['effective_session']=='24h'
    assert len(r['source_bars'])==3
    assert r['bars'][-1]['volume']==33


def test_empty_context_still_includes_known_minutes_in_partial_bucket():
    r=BacktestService(Market()).replay_bars(symbol='AAPL',timeframe='5m',session='regular',replay_date=pd.Timestamp('2026-06-02').date(),start_time='10:02',context_bars=0)
    assert len(r['bars'])==1 and len(r['source_bars'])==3
    assert pd.Timestamp(r['bars'][0]['timestamp'])==pd.Timestamp('2026-06-02T14:00:00Z')


def test_start_before_first_available_minute_advances_to_available_bar():
    r=BacktestService(Market()).replay_bars(symbol='AAPL',timeframe='5m',session='regular',replay_date=pd.Timestamp('2026-06-02').date(),start_time='08:00',context_bars=0)
    assert pd.Timestamp(r['frontier'])==pd.Timestamp('2026-06-02T13:30:00Z')
    assert len(r['source_bars'])==1 and r['bars'][0]['volume']==10


def test_api_default_response_and_indicator_do_not_include_future_data():
    app=FastAPI(); app.state.services=SimpleNamespace(backtest=BacktestService(Market()))
    app.include_router(router,prefix='/api')
    with TestClient(app) as client:
        params=dict(symbol='AAPL',timeframe='5m',session='regular',replay_date='2026-06-02',start_time='10:02',context_bars=10)
        response=client.get('/api/strategy-lab/replay/bars',params=params)
        assert response.status_code==200
        payload=response.json()
        assert all(pd.Timestamp(b['timestamp'])<=pd.Timestamp(payload['frontier']) for b in payload['source_bars'])
        indicator=client.get('/api/strategy-lab/replay/indicator',params={**params,'key':'volume'})
        assert indicator.status_code==200
        assert indicator.json()['values'][-1]['value']==payload['bars'][-1]['volume']
        assert client.get('/api/strategy-lab/replay/bars',params={**params,'frontier':'2026-06-02T15:00:00'}).status_code==400
