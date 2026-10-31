import pandas as pd
import pytest
from app.backtesting.strategies.iof_v2_persistent_zones import Zone
from tools.run_iofv2_combined import selected_zones, config_risk, run_configs


def zone(tf, key, entry):
    stamp=pd.Timestamp('2025-01-06T00:02:00Z')
    return Zone(key,tf,'long',entry-2,entry,entry,entry-2,1.,stamp,
                stamp-pd.Timedelta(hours=4),5,.9,2.,True,False)


def frame():
    stamps=pd.date_range('2025-01-06T00:00:00Z',periods=7,freq='min')
    ohlc=[(104.,105.,103.,104.),(104.,105.,103.,104.),(104.,105.,103.,104.),
          (104.,104.,100.5,101.),(101.,102.,100.5,101.5),
          (101.5,102.,100.8,101.7),(101.7,102.,100.8,101.3)]
    return pd.DataFrame([dict(timestamp=t,open=x[0],high=x[1],low=x[2],close=x[3])
                         for t,x in zip(stamps,ohlc)])


def test_selection_does_not_duplicate_higher_timeframe():
    a=zone('15m','15m:basic:a',101.);b=zone('4h','4h:basic:b',102.)
    assert [z.zone_id for z in selected_zones([a],[b],'combined_1slot')]==[a.zone_id,b.zone_id]
    assert len(selected_zones([a],[b],'15m_only'))==1
    assert len(selected_zones([a],[b],'4h_only'))==1
    with pytest.raises(ValueError,match='Duplicate'):
        selected_zones([a],[a],'combined_1slot')


def test_two_slot_conservatively_splits_risk():
    assert config_risk('combined_1slot',1.,.5)==(1,1.)
    assert config_risk('combined_2slots',1.,.5)==(2,.5)


def test_shared_one_vs_two_slot_both_use_same_account():
    a=zone('15m','15m:basic:a',101.);b=zone('4h','4h:basic:b',102.)
    results=list(run_configs(frame(),[a],[b],configurations=('combined_1slot','combined_2slots'),
                             entry_modes=('single',), max_leverage=200.,step_price=.5,max_rungs=4))
    one=results[0][2];two=results[1][2]
    assert one['campaigns']==1
    assert two['campaigns']==2
    assert one['4h_completed_campaigns']+one['15m_completed_campaigns']==1
    assert two['4h_completed_campaigns']==two['15m_completed_campaigns']==1
    assert two['nominal_max_active_risk_pct']==1.
    assert all('timeframe' in ev for ev in results[1][4])


def test_standalone_result_identical_to_original_runner():
    from tools.run_iofv2_ladder import run_ladder
    a=zone('15m','15m:basic:a',101.)
    df=frame()
    original=run_ladder(df,[a],max_leverage=200.,step_price=.5,max_rungs=4,
                        entry_mode='single')
    selected=list(run_configs(df,[a],[],configurations=('15m_only',),entry_modes=('single',),
                              max_leverage=200.,step_price=.5,max_rungs=4))
    assert selected[0][2]['return_pct']==original[0]['return_pct']
    assert selected[0][2]['campaigns']==original[0]['campaigns']
    assert selected[0][3][0]['net_pnl']==original[1][0]['net_pnl']


def test_reject_more_than_shared_risk_ceiling():
    with pytest.raises(ValueError):
        list(run_configs(frame(),[],[],configurations=('combined_2slots',),
             entry_modes=('single',), risk_pct=1.,two_slot_risk_pct=.7))
