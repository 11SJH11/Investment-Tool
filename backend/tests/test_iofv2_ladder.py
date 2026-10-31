"""Deterministic, no-market-data tests for IOF V2 ladder research simulator."""
import math
import pandas as pd

from app.backtesting.strategies.iof_v2_persistent_zones import Zone
from tools.run_iofv2_ladder import make_rungs, run_ladder


def zone(*, direction='long', entry=101., stop=99.,
         confirmed='2025-01-06T00:02:00Z', key='zone-a'):
    t=pd.Timestamp(confirmed)
    return Zone(key,'15m',direction,entry-2 if direction=='long' else entry,
                entry if direction=='long' else entry+2,
                entry,stop,1.,t,t-pd.Timedelta(minutes=60),5,.9,2.,True,True)


def frame(prices):
    """Each tuple is O H L C for a completed minute, start 00:00 UTC."""
    t=pd.Timestamp('2025-01-06T00:00:00Z')
    return pd.DataFrame([dict(timestamp=t+pd.Timedelta(minutes=i),
                              open=o,high=h,low=l,close=c)
                         for i,(o,h,l,c) in enumerate(prices)])


def test_exact_price_rungs_do_not_pass_stop():
    p,w=make_rungs(zone(),step_price=.5,max_rungs=99)
    assert p==[101.,100.5,100.,99.5]
    assert abs(sum(w)-1.)<1e-10
    assert all(x>99 for x in p)


def test_single_mode_one_rung():
    p,w=make_rungs(zone(),step_price=.1,max_rungs=99,entry_mode='single')
    assert p==[101.] and w==[1.]


def test_frontloaded_risk_more_for_top_edge():
    _,w=make_rungs(zone(),step_price=.5,max_rungs=4,allocation='front_loaded')
    assert len(w)==4 and w[0]>w[1]>w[2]>w[3]
    assert math.isclose(sum(w),1.)
    p,_=make_rungs(zone(),step_price=.5,max_rungs=4,allocation='front_loaded')
    lots=[w[i]/abs(p[i]-99.) for i in range(len(p))]
    assert all(lots[i+1]<lots[i] for i in range(len(lots)-1))


def test_old_zone_survives_weeks_before_first_fill():
    z=zone(confirmed='2024-12-01T00:00:00Z')
    f=frame([(104.,104.5,103.5,104.),(104.,104.4,103.,103.8),
             (103.8,104.,100.8,101.5),(101.5,102.,101.2,101.8)])
    s,trades,events,_=run_ladder(f,[z],step_price=.5,max_rungs=4)
    assert s['campaigns']==1
    assert trades[0]['zone_age_days']>30
    assert any(x['event']=='ENTRY' for x in events)


def test_zone_not_available_on_confirmation_candle():
    z=zone(confirmed='2025-01-06T00:03:00Z')
    f=frame([(104.,104.5,103.5,104.),(104.,104.5,103.5,104.),
             (104.,104.5,98.0,104.)])
    s,_,events,_=run_ladder(f,[z],step_price=.5,max_rungs=4)
    assert s['campaigns']==0 and not events


def test_all_depth_rungs_share_a_single_risk_budget_at_stop():
    z=zone()
    f=frame([(104.,104.5,103.5,104.),(104.,104.5,103.5,104.),
             (104.,104.5,103.5,104.),(104.,104.5,98.5,99.)])
    s,trades,events,_=run_ladder(f,[z],risk_pct=1.,max_leverage=200.,
                                  step_price=.5,max_rungs=4)
    assert s['campaigns']==1
    assert trades[0]['rungs_filled']==4
    assert trades[0]['net_pnl']<=0
    assert abs(trades[0]['net_pnl'])<=101.0
    assert math.isclose(trades[0]['actually_allocated_risk_cash'],100.,rel_tol=1e-8)
    assert all(x['event']=='STOP' for x in events if x['event']!='ENTRY')


def test_no_target_credit_from_same_bar_as_limit_entry():
    z=zone()
    f=frame([(104.,105.,103.,104.),(104.,105.,103.,104.),
             (104.,105.,103.,104.),(104.,109.,100.8,104.)])
    s,trades,events,_=run_ladder(f,[z],max_leverage=200.,step_price=.5,max_rungs=1)
    assert s['campaigns']==1  # closed as END_OF_DATA
    assert not any(x['event'].startswith('TP') for x in events)
    assert 'END_OF_DATA' in trades[0]['events']


def test_worst_fills_closed_first_at_tp1_and_tp2():
    z=zone()
    f=frame([(104.,104.5,103.5,104.),(104.,104.5,103.5,104.),
             (104.,104.5,103.5,104.),(104.,104.5,100.2,100.8), # edge + second rung
             (100.8,103.2,100.7,102.9),  # TP1 at 103
             (102.9,105.5,102.8,105.),  # TP2 at 105
             (105.,108.,104.9,107.2)]) # TP3 at 107, close
    s,trades,events,_=run_ladder(f,[z],max_leverage=200.,step_price=.5,max_rungs=2)
    assert s['campaigns']==1
    assert trades[0]['rungs_filled']==2
    tp1=[e for e in events if e['event']=='TP1_WORST_FIRST']
    tp2=[e for e in events if e['event']=='TP2_WORST_FIRST']
    assert tp1 and tp2
    assert tp1[0]['rung']==0  # highest buy = worst fill
    assert trades[0]['tp2']


def test_breakeven_after_tp2_disables_other_rungs():
    z=zone()
    f=frame([(104.,104.5,103.5,104.),(104.,104.5,103.5,104.),
             (104.,104.5,103.5,104.),(104.,104.5,100.8,101.5),
             (101.5,103.5,101.5,103.3), # TP1
             (103.3,105.1,103.2,105.), # TP2
             (105.,105.2,100.,101.), # revisit multiple levels after TP2
             (101.,104.,100.,103.)])
    s,trades,events,states=run_ladder(f,[z],max_leverage=200.,step_price=.25,max_rungs=8)
    assert s['campaigns']==1
    assert trades[0]['rungs_filled']==1
    assert trades[0]['tp2'] is True
    assert len([e for e in events if e['event']=='ENTRY'])==1
    assert states[0]['status'] in ('be_after_tp2','tp3','tp2_flat')


def test_short_ladder_direction():
    z=zone(direction='short',entry=99.,stop=101.,key='short')
    f=frame([(96.,96.4,95.8,96.),(96.,96.4,95.8,96.),
             (96.,96.4,95.8,96.),(96.,101.5,95.5,101.)])
    s,trades,events,_=run_ladder(f,[z],max_leverage=200.,step_price=.5,max_rungs=4)
    assert s['campaigns']==1
    assert trades[0]['rungs_filled']==4
    assert trades[0]['net_pnl']<0


def test_leverage_caps_loss_even_with_many_rungs():
    z=zone()
    f=frame([(104.,105.,103.,104.),(104.,105.,103.,104.),
             (104.,105.,103.,104.),(104.,105.,98.,99.)])
    s,trades,_,_=run_ladder(f,[z],max_leverage=1.,step_price=.5,max_rungs=4)
    assert trades[0]['actually_allocated_risk_cash']<100
    assert trades[0]['net_pnl']<0


def test_gold_four_hour_session_anchor_dst_aware():
    from tools.run_iofv2_reference import candles_for_timeframe
    # Winter: NY 17:00 = UTC 22:00, so first full 4h bucket is 22-02 UTC.
    t=pd.Timestamp('2025-01-06T22:00:00Z')
    rows=[dict(timestamp=t+pd.Timedelta(minutes=i),open=100.,high=101.,low=99.,close=100.)
          for i in range(240)]
    frame,dropped=candles_for_timeframe(pd.DataFrame(rows),'4h',market='gold')
    assert len(frame)==1 and dropped==0
    assert frame.iloc[0]['timestamp']==t


def test_equity_timeframes_regular_session_aligned_0930_ny():
    from tools.run_iofv2_reference import candles_for_timeframe
    t=pd.Timestamp('2025-01-06T14:30:00Z')  # 09:30 in winter NY
    rows=[dict(timestamp=t+pd.Timedelta(minutes=i),open=100.,high=101.,low=99.,close=100.)
          for i in range(390)]
    frame,dropped=candles_for_timeframe(pd.DataFrame(rows),'4h',market='equity')
    assert len(frame)==1 and dropped>=1  # 240m complete, 150m partial
    assert frame.iloc[0]['timestamp']==t


def test_same_runner_single_vs_ladder_uses_different_number_of_entries():
    z=zone()
    f=frame([(104.,105.,103.,104.),(104.,105.,103.,104.),
             (104.,105.,103.,104.),(104.,105.,100.1,100.5),
             (100.5,101.,98.9,99.)])
    base,bt,_,_=run_ladder(f,[z],max_leverage=200.,entry_mode='single',step_price=.5,max_rungs=4)
    ladder,lt,_,_=run_ladder(f,[zone()],max_leverage=200.,entry_mode='ladder',step_price=.5,max_rungs=4)
    assert bt[0]['rungs_filled']==1
    assert lt[0]['rungs_filled']==4  # price crosses all four depths before the shared stop
    assert ladder['campaigns']==base['campaigns']==1
