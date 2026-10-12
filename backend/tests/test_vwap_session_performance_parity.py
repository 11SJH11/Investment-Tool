"""Exact parity with the pre-audit session normalizer, including prefix exposure."""
import numpy as np
import pandas as pd
import pytest
from app.backtesting.strategies import vwap_trend_entry_exit_distance_research_v4 as v4
from tests.fixtures.vwap_session_reference import normalise_1m


@pytest.mark.parametrize('kind',['utc','naive','strings','new_york'])
def test_session_normalization_exact_reference_and_prefixes(kind):
    stamps=pd.date_range('2026-03-06 13:00',periods=1200,freq='min',tz='UTC').append(
        pd.date_range('2026-03-09 12:00',periods=1200,freq='min',tz='UTC'))
    if kind=='naive':stamps=stamps.tz_localize(None)
    if kind=='strings':stamps=stamps.astype(str)
    if kind=='new_york':stamps=stamps.tz_convert('America/New_York')
    frame=pd.DataFrame({'timestamp':stamps,'close':np.arange(len(stamps),dtype=float),'volume':10})
    frame.index=np.arange(len(frame))*3
    original=frame.copy(deep=True)
    for end in [0,1,90,91,300,480,800,1400,len(frame)]:
        prefix=frame.iloc[:end]
        pd.testing.assert_frame_equal(v4._normalise_1m(prefix),normalise_1m(prefix),check_exact=True)
    expected=normalise_1m(frame)
    expected=expected.loc[expected['_date']==expected.iloc[-1]['_date']].reset_index(drop=True)
    pd.testing.assert_frame_equal(v4._today_rth(frame),expected,check_exact=True)
    result=v4._normalise_1m(frame);result.loc[:,'close']=-1
    pd.testing.assert_frame_equal(frame,original,check_exact=True)


@pytest.mark.parametrize('frame',[None,pd.DataFrame(),pd.DataFrame({'close':[1]}),
    pd.DataFrame({'timestamp':[pd.NaT]}),pd.DataFrame({'timestamp':['2026-01-02T12:00Z']})])
def test_empty_invalid_and_outside_session_reference(frame):
    pd.testing.assert_frame_equal(v4._normalise_1m(frame),normalise_1m(frame),check_exact=True)


@pytest.mark.parametrize('key,extra',[
    ('vwap_trend_entry_exit_distance_research_v4',{}),
    ('vwap_trend_confirmation_quality_research_v5',{'min_confirmation_displacement_bps':6}),
    ('vwap_d6_mss15_research_v1',{}),
    ('vwap_d6_midvol_research_v1',{}),
    ('vwap_d6_swing_s5_causal_sweep_research_v1',{}),
])
def test_engine_results_exact_with_original_normalizer(monkeypatch,key,extra):
    import json
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    from app.backtesting.strategies import strategy_registry
    if key not in strategy_registry._items:
        pytest.skip('Optional locally installed confluence variant is unavailable')
    stamps=pd.date_range('2026-03-06 14:30',periods=90,freq='min',tz='UTC').append(
        pd.date_range('2026-03-09 13:30',periods=90,freq='min',tz='UTC'))
    x=np.arange(len(stamps));close=100+np.sin(x/4)*.5+x*.0005
    frame=pd.DataFrame(dict(timestamp=stamps,open=close-.02,high=close+.1,low=close-.1,close=close,volume=100+x))
    higher=frame.set_index('timestamp').resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna().reset_index()
    def run():
        strategy=strategy_registry.create(key,trend_timeframe='off',**extra)
        result=BacktestEngine(BacktestConfig(sizing_mode='position_pct',risk_value=100,allow_overnight=False)).run(
            symbol_frames={'QQQ':{'1m':frame,'15m':higher}},strategies={'QQQ':strategy},primary_timeframe='1m')
        return json.dumps(result,sort_keys=True,default=str)
    optimized=run()
    monkeypatch.setattr(v4,'_normalise_1m',normalise_1m)
    original=run()
    assert optimized==original  # Includes every trade/metadata/rejection, equity point, metric and analysis.
    if key in {'vwap_trend_entry_exit_distance_research_v4','vwap_trend_confirmation_quality_research_v5'}:
        assert len(json.loads(original)['trades'])>0
