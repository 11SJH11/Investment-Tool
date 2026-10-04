from copy import deepcopy
import pandas as pd
import pytest
from app.services.trade_review import reconstruct
from app.backtesting.review_contracts import LEGACY
from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import _vwap

KEY="vwap_trend_entry_exit_distance_research_v4"
def fixture():
    times=pd.date_range('2026-09-28T13:30Z',periods=8,freq='min')
    closes=[100,102,104,106,100,98,97,96]
    frame=pd.DataFrame({'timestamp':times,'open':closes,'high':closes,'low':closes,'close':closes,'volume':[100]*8})
    trade={'symbol':'SPY','entry_time':str(times[4]),'exit_time':str(times[6]),'entry_price':100,'exit_price':97,'direction':'long','exit_reason':'vwap_confirmed_reverse','metadata':{'vwap':103,'confirmation_count':3}}
    config={'strategy_params':{'entry_confirmation_bars':3,'exit_confirmation_bars':2,'max_entry_vwap_distance_bps':25}}
    return frame,trade,config

def test_vwap_matches_strategy_prefixes_and_bands_and_reset():
    frame,trade,config=fixture()
    future=frame.iloc[:1].copy();future.timestamp+=pd.Timedelta(days=1);future[['high','low','close']]=500
    allbars=pd.concat([frame,future],ignore_index=True)
    review=reconstruct({'1m':allbars},trade,config,LEGACY[KEY])
    points=review['series'][0]['points']
    for i in range(len(frame)):assert points[i]['value']==pytest.approx(_vwap(frame.iloc[:i+1]))
    assert points[-1]['value']==500
    assert review['series'][1]['points'][3]['value']==pytest.approx(points[3]['value']*1.0025)
    assert review['series'][2]['points'][3]['value']==pytest.approx(points[3]['value']*.9975)

def test_confirmations_and_evidence_are_causal():
    frame,trade,config=fixture()
    review=reconstruct({'1m':frame},trade,config,LEGACY[KEY])
    assert [pd.Timestamp(h['timestamp']) for h in review['highlights'] if h['kind']=='entry']==list(frame.timestamp.iloc[1:4])
    assert [pd.Timestamp(h['timestamp']) for h in review['highlights'] if h['kind']=='exit']==list(frame.timestamp.iloc[4:6])
    changed=frame.copy();changed.loc[6:,['high','low','close']]=9999
    second=reconstruct({'1m':changed},trade,config,LEGACY[KEY])
    assert review['evidence']==second['evidence']
    assert review['highlights']==second['highlights']
    recorded=deepcopy(trade);recorded['metadata']['review_entry']={'signal_time':str(frame.timestamp.iloc[3]+pd.Timedelta(minutes=1)),'signal_close':106,'confirmation_observed':3}
    fields=reconstruct({'1m':frame},recorded,config,LEGACY[KEY])['evidence']['entry']
    assert next(f for f in fields if f['label']=='Signal close')['value']==106

def test_generic_daily_ema_and_optional_missing_indicator():
    frame,trade,config=fixture()
    daily=frame.iloc[:4].copy();daily.timestamp=pd.date_range('2026-09-24T13:30Z',periods=4,freq='D');daily['available_at']=daily.timestamp+pd.Timedelta(hours=6,minutes=30)
    declaration={'series':[{'id':'ema','indicator':'ema','timeframe':'1d','params':{'length':2}},{'id':'missing','indicator':'not-installed'}]}
    review=reconstruct({'1m':frame,'1d':daily},trade,config,declaration)
    assert len(review['series'])==1 and review['warnings']
    assert pd.Timestamp(review['series'][0]['points'][0]['available_at'])==daily.available_at.iloc[1]
    changed=daily.copy();changed.loc[3,'close']=9999
    again=reconstruct({'1m':frame,'1d':changed},trade,config,declaration)
    assert review['series'][0]['points'][:-1]==again['series'][0]['points'][:-1]

def test_legacy_no_declaration_and_no_bars_remain_readable():
    _,trade,config=fixture()
    review=reconstruct({},trade,config,{})
    assert review['series']==[] and review['evidence']['entry']
    assert review['evidence']['entry'][0]['provenance']=='not_recorded'


def test_recording_does_not_change_v4_execution(monkeypatch):
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import VwapTrendEntryExitDistanceResearchV4
    import app.backtesting.review_contracts as contracts
    frame,_,_=fixture()
    def run():
        strategy=VwapTrendEntryExitDistanceResearchV4(trend_timeframe='off',entry_confirmation_bars=3,exit_confirmation_bars=2)
        return BacktestEngine(BacktestConfig(sizing_mode='quantity',risk_value=1)).run(symbol_frames={'SPY':{'1m':frame}},strategies={'SPY':strategy},primary_timeframe='1m')
    recorded=run()
    assert recorded['trades'] and 'review_entry' in recorded['trades'][0]['metadata']
    assert 'review_exit' in recorded['trades'][0]['metadata']
    monkeypatch.setattr(contracts,'record_decision',lambda *args:None)
    original=run()
    for trade in recorded['trades']:
        trade['metadata'].pop('review_entry',None);trade['metadata'].pop('review_exit',None)
    # Setup metadata intentionally receives recorded entry evidence as well.
    assert recorded['trades']==original['trades']
    assert recorded['metrics']==original['metrics']
    assert recorded['equity_curve']==original['equity_curve']


def test_reference_htf_adapter_uses_same_canonical_state_without_future_daily_closes():
    from app.indicators.rth_trend import RthTrendEMA
    from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import VwapTrendEntryExitDistanceResearchV4
    from app.backtesting.context import StrategyContext
    rows=[]
    for day in range(3):
        stamps=pd.date_range(pd.Timestamp('2026-09-28T13:30Z')+pd.Timedelta(days=day),periods=390,freq='min')
        for stamp in stamps:rows.append({'timestamp':stamp,'open':100+day,'high':100+day,'low':100+day,'close':100+day,'volume':100})
    frame=pd.DataFrame(rows)
    got=RthTrendEMA().calculate(frame,length=2,timeframe='1d')
    strategy=VwapTrendEntryExitDistanceResearchV4(trend_timeframe='1d',trend_ema_length=2);strategy.reset()
    stamp=frame.timestamp.iloc[780]+pd.Timedelta(minutes=1)
    ctx=StrategyContext(symbol='SPY',primary_timeframe='1m',decision_time=stamp.to_pydatetime(),frames={'1m':frame},position=None,equity=0)
    assert got.iloc[780]==pytest.approx(strategy._trend_state(ctx)[2])
    changed=frame.copy();changed.loc[781:,'close']=9999
    other=RthTrendEMA().calculate(changed,length=2,timeframe='1d')
    pd.testing.assert_series_equal(got.iloc[:781],other.iloc[:781])
    assert pd.isna(got.iloc[389]) and pd.isna(got.iloc[390])


def test_api_review_and_sections_preserve_saved_facts_when_history_unavailable(tmp_path):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.strategy_lab import router,get_services
    from app.storage.database import Database
    from app.storage.backtest_run_repository import BacktestRunRepository
    frame,trade,config=fixture()
    db=Database(tmp_path/'api.db');db.initialize();repo=BacktestRunRepository(db)
    saved=repo.create(config=config,result={'strategy':{'key':KEY},'primary_timeframe':'1m','session':'regular','trades':[trade],'metrics':{'trades':1}})
    def unavailable(**kwargs):raise RuntimeError('private provider detail')
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=SimpleNamespace(runs=repo,audit_bars=unavailable))
    with TestClient(app) as client:
        summary=client.get(f"/strategy-lab/runs/{saved['id']}/sections/summary")
        assert summary.status_code==200 and 'trades' not in summary.json()['result']
        response=client.get(f"/strategy-lab/runs/{saved['id']}/trades/0/review")
        assert response.status_code==200
        assert response.json()['trade']==trade and response.json()['bars']==[]
        assert 'private provider detail' not in response.text
        assert client.get(f"/strategy-lab/runs/{saved['id']}/trades/-1/review").status_code==400
    assert repo.get(saved['id'])==saved
