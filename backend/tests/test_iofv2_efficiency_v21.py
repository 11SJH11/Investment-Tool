"""Reproducibility and fill-cost regressions for IOF V2 efficiency v2.1."""
import math
import pandas as pd
import pytest

from app.backtesting.strategies.iof_v2_persistent_zones import DisplacementDetector, Zone
from tools.run_iofv2_ladder import run_ladder


def _zone(direction='long'):
    t = pd.Timestamp('2025-01-06T00:02:00Z')
    if direction == 'long':
        return Zone('long','15m','long',99,101,101,99,1,t,t,5,.8,2,True,True)
    return Zone('short','15m','short',99,101,99,101,1,t,t,5,.8,2,True,True)


def _df(ohlc):
    base = pd.Timestamp('2025-01-06T00:00:00Z')
    return pd.DataFrame([dict(timestamp=base+pd.Timedelta(minutes=i),
                              open=o, high=h,low=l,close=c)
                         for i,(o,h,l,c) in enumerate(ohlc)])


def test_normalized_efficiency_includes_base_to_impulse_bridge():
    det=DisplacementDetector('15m')
    # 30 prior candles with a bearish base far from the leg's immediately prior close.
    history=[]
    for i in range(30):
        o,c=(100.25,100.0) if i==20 else (101.7,102.0)
        history.append(dict(timestamp=pd.Timestamp('2025-01-02T00:00:00Z')+
                            pd.Timedelta(minutes=15*i),
                            open=o,close=c,high=max(o,c)+.1,low=min(o,c)-.1))
    det.history.extend(history)
    leg=det._new_leg(1,atr=1.,prior_close=102.)
    assert leg is not None
    assert leg['base']['close']==100.
    assert leg['path']==pytest.approx(2.)
    # Price rises to 103; numerator=3, total close-to-close path=2+1=3,
    # so efficiency cannot exceed 1. Without the bridge it would be 3.0.
    leg['path']+=abs(103.-102.)
    efficiency=(103.-leg['base']['close'])/leg['path']
    assert efficiency==pytest.approx(1.)


def test_detector_emitted_efficiencies_are_normalized():
    detector=DisplacementDetector('1m',displacement_atr=1.,min_efficiency=.3)
    start=pd.Timestamp('2025-01-06T00:00:00Z')
    emitted=[]
    for i in range(100):
        o=100+i*.05 if i>=30 else 100+(i%3)*.1
        c=o+(.2 if i>=30 else (-.2 if i%2 else .2))
        z=detector.process(dict(timestamp=start+pd.Timedelta(minutes=i),
                    open=o,high=max(o,c)+.10,low=min(o,c)-.10,close=c))
        if z:emitted.append(z)
    assert emitted
    assert all(0<=z.efficiency<=1 for z in emitted)


def test_zero_cost_argument_is_exactly_backward_compatible():
    df=_df([(104,105,103,104)]*3 + [(104,104,100.8,101.5),
           (101.5,103.5,101.5,103.3),(103.3,105.2,103.2,105.1),
           (105.1,108,105,107.2)])
    a=run_ladder(df,[_zone()],max_leverage=200,step_price=.5,max_rungs=2)
    b=run_ladder(df,[_zone()],max_leverage=200,step_price=.5,max_rungs=2,
                 spread_price=0,slippage_price=0)
    assert a==b
    assert a[0]['zero_cost_research'] is True


def test_spread_reduces_profitable_trade_and_is_visible_in_events():
    df=_df([(104,105,103,104)]*3 + [(104,104,100.8,101.5),
           (101.5,103.5,101.5,103.3),(103.3,105.2,103.2,105.1),
           (105.1,108,105,107.2)])
    a=run_ladder(df,[_zone()],max_leverage=200,step_price=.5,max_rungs=1,
                 entry_mode='single')
    b=run_ladder(df,[_zone()],max_leverage=200,step_price=.5,max_rungs=1,
                 entry_mode='single',spread_price=.20,slippage_price=.02)
    assert a[0]['campaigns']==b[0]['campaigns']==1
    assert b[0]['ending_balance']<a[0]['ending_balance']
    assert b[0]['zero_cost_research'] is False
    assert b[2][0]['event']=='ENTRY'
    assert b[2][0]['price']==pytest.approx(a[2][0]['price']+.12)
    assert b[1][0]['actually_allocated_risk_cash']<=b[1][0]['risk_budget']+1e-7


def test_short_spread_pays_sell_bid_buy_ask():
    df=_df([(96,96.5,95.5,96)]*3 + [(96,99.1,95.5,98.7),
           (98.7,98.9,96.5,96.6),(96.6,96.8,94.5,94.9)])
    a=run_ladder(df,[_zone('short')],max_leverage=200,step_price=.5,max_rungs=1,
                 entry_mode='single',spread_price=0.)
    b=run_ladder(df,[_zone('short')],max_leverage=200,step_price=.5,max_rungs=1,
                 entry_mode='single',spread_price=.20)
    assert a[0]['campaigns']==b[0]['campaigns']==1
    assert b[2][0]['price']==pytest.approx(a[2][0]['price']-.10)


def test_invalid_costs_rejected():
    with pytest.raises(ValueError):run_ladder(_df([(104,105,103,104)]),[_zone()],spread_price=-.1)
    with pytest.raises(ValueError):run_ladder(_df([(104,105,103,104)]),[_zone()],slippage_price=-.1)
