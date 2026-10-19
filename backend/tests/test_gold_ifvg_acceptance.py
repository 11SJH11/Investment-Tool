"""Synthetic acceptance of the unchanged, source-reconciled Gold IFVG baseline."""
from datetime import date

import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.backtesting.strategies.gold_asia_15m_ifvg_research_v1 import (
    GoldAsia15mIfvgResearchV1, _asia_session_key, _asia_session_end,
)
from app.data.instruments import default_trading_weekdays


def fixture(day, outcome='target'):
    start=pd.Timestamp(day+' 20:00',tz='America/New_York').tz_convert('UTC')
    candles=[(3000,3002,2998,3001),(3002,3008,3001,3007),
             (3007,3010,3005,3008),(3008,3009,2999,3001)]
    rows=[]
    for i,(o,h,l,c) in enumerate(candles):
        for minute in range(15):
            rows.append((start+pd.Timedelta(minutes=15*i+minute),o if minute==0 else c,
                         h if minute==0 else c,l if minute==0 else c,c,1))
    if outcome=='target': tail=[(3001,3002,2991,2992)]
    elif outcome=='stop': tail=[(3001,3011,3000,3010)]
    else: tail=[(3001,3002,2994,2995),(2995,3002,2994,3001)]
    rows.extend((start+pd.Timedelta(minutes=60+i),*bar,1) for i,bar in enumerate(tail))
    one=pd.DataFrame(rows,columns=['timestamp','open','high','low','close','volume'])
    fifteen=one.iloc[:60].set_index('timestamp').resample('15min').agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).reset_index()
    return {'1m':one,'15m':fifteen}


@pytest.mark.parametrize('day',['2026-01-04','2026-03-08','2026-11-01'])
@pytest.mark.parametrize('outcome,expected',[('target',1),('stop',-1),('breakeven',0)])
def test_sunday_completed_signals_fills_and_management(day,outcome,expected):
    frames=fixture(day,outcome)
    result=BacktestEngine(BacktestConfig(trading_weekdays=default_trading_weekdays(['XAUUSD']))).run(
        symbol_frames={'XAUUSD':frames},strategies={'XAUUSD':GoldAsia15mIfvgResearchV1()},primary_timeframe='1m')
    assert not result['rejected_signals']
    assert len(result['trades'])==1
    trade=result['trades'][0]
    assert trade['entry_price']==3001 and trade['stop_loss']==3010 and trade['take_profit']==2992
    assert pd.Timestamp(trade['entry_time'])==frames['1m'].timestamp.iloc[60]
    assert trade['metadata']['asia_session_key']==day
    assert trade['r_multiple']==pytest.approx(expected)
    assert trade['metadata']['target_risk_amount']==100
    assert trade['quantity']==pytest.approx(10000/3001)
    assert trade['initial_risk_amount']==pytest.approx(9*10000/3001)
    assert trade['metadata']['initial_notional_exposure']==pytest.approx(10000)
    assert trade['metadata']['sizing_limited'] is True
    if outcome=='breakeven':
        assert trade['metadata']['final_stop_loss']==3001
        assert pd.Timestamp(trade['exit_time'])==frames['1m'].timestamp.iloc[61]


def test_explicit_weekday_restriction_still_rejects_sunday():
    result=BacktestEngine(BacktestConfig(trading_weekdays=(0,1,2,3,4))).run(
        symbol_frames={'XAUUSD':fixture('2026-01-04')},
        strategies={'XAUUSD':GoldAsia15mIfvgResearchV1()},primary_timeframe='1m')
    assert result['trades']==[]
    assert result['rejected_signals']


@pytest.mark.parametrize('day',['2026-01-04','2026-03-08','2026-11-01'])
def test_asia_uses_local_start_date_and_excludes_midnight(day):
    start=pd.Timestamp(day+' 20:00',tz='America/New_York')
    assert _asia_session_key(start)==date.fromisoformat(day)
    assert _asia_session_key(start-pd.Timedelta(minutes=1)) is None
    assert _asia_session_key(_asia_session_end(date.fromisoformat(day))) is None


def test_market_defaults_are_entry_eligibility_not_equity_for_all():
    assert default_trading_weekdays(['XAUUSD'])==(0,1,2,3,4,6)
    assert default_trading_weekdays(['NQ1!'])==(0,1,2,3,4,6)
    assert default_trading_weekdays(['AAPL'])==(0,1,2,3,4)


def test_future_inversion_bar_is_not_visible_before_completion():
    frames=fixture('2026-01-04')
    frames['1m']=frames['1m'].iloc[:59]
    result=BacktestEngine(BacktestConfig(trading_weekdays=default_trading_weekdays(['XAUUSD']))).run(
        symbol_frames={'XAUUSD':frames},strategies={'XAUUSD':GoldAsia15mIfvgResearchV1()},primary_timeframe='1m')
    assert result['trades']==[] and result['setups']==[]
