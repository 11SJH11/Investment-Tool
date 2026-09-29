import pandas as pd
import pytest

from app.backtesting.context import StrategyContext
from app.backtesting.strategies.intraday_baselines import OpeningRangeResearch, OpeningRangeBreakout, _OpeningRangeResearchRules, ORB_DEFAULTS
from app.backtesting.strategies.orb_participation import diagnostics, DEFAULTS, FIELDS, wilder_atr
from tests.test_intraday_baselines import orb_frame, simulate


def history():
    days=pd.bdate_range('2025-08-01',periods=80)
    daily=pd.DataFrame(dict(timestamp=pd.DatetimeIndex(days).tz_localize('America/New_York')+pd.Timedelta(hours=9,minutes=30),open=100.,high=102.,low=98.,close=100.,volume=10000.))
    minute=[]
    for i,day in enumerate(days[-20:]):
        f=orb_frame(day.strftime('%Y-%m-%d')).iloc[:16].copy()
        f['volume']=100*(i+1)
        # The same 09:45 minute is deliberately different from neighbouring minutes.
        f.loc[f.index[-1],'volume']=10*(i+1)
        minute.append(f)
    signal_day=(days[-1]+pd.offsets.BDay()).strftime('%Y-%m-%d')
    signal=orb_frame(signal_day)
    signal.loc[15,['open','high','low','close','volume']]=[101,104,100,103,210]
    all_minute=pd.concat([*minute,signal],ignore_index=True)
    decision=signal.iloc[15].timestamp+pd.Timedelta(minutes=1)
    def ctx(m=all_minute,d=daily,at=decision):
        return StrategyContext(symbol='AAPL',primary_timeframe='1m',decision_time=at.to_pydatetime(),frames={'1m':m,'1d':d},position=None,equity=1e6)
    return all_minute,daily,ctx


def test_exact_candle_prior_atr_and_same_minute_medians():
    _,_,ctx=history();m=diagnostics(ctx(),15)
    assert m['breakout_range']==4 and m['breakout_body']==2
    assert m['breakout_body_ratio']==.5 and m['breakout_close_location']==.75
    assert m['prior_1m_atr14']==2 and m['breakout_range_atr']==2
    assert m['breakout_volume']==210
    assert m['same_minute_volume_median20']==105
    assert m['breakout_rvol']==2
    assert m['opening_range_volume']==1500
    assert m['opening_range_volume_median20']==15750
    assert m['opening_range_rvol']==pytest.approx(1500/15750)
    assert m['previous_daily_atr14']==4 and m['previous_close']==100
    assert m['daily_natr_pct']==4 and m['daily_natr_percentile']==100


def test_no_future_or_current_daily_data_and_atr_excludes_breakout():
    minute,daily,ctx=history();expected=diagnostics(ctx(),15)
    future=minute.iloc[-1:].copy();future[['high','volume']]=1e9
    future_daily=daily.iloc[-1:].copy();future_daily['timestamp']=minute.iloc[-1].timestamp.normalize()+pd.Timedelta(hours=9,minutes=30);future_daily[['high','volume']]=1e9
    assert diagnostics(ctx(m=pd.concat([minute,future]),d=pd.concat([daily,future_daily])),15)==expected
    changed=minute.copy();changed.loc[len(changed)-3,'high']=1000
    assert diagnostics(ctx(m=changed),15)['prior_1m_atr14']==expected['prior_1m_atr14']
    # Signal bar is not completed one second before its close.
    early=ctx(at=minute.iloc[-3].timestamp+pd.Timedelta(seconds=59))
    assert OpeningRangeResearch().on_bar(early) is None


def test_missing_recent_session_minute_does_not_backfill_older_session():
    minute,daily,ctx=history()
    local=minute.timestamp.dt.tz_convert('America/New_York')
    remove=(local.dt.date==daily.iloc[-1].timestamp.date())&(local.dt.hour==9)&(local.dt.minute==45)
    m=diagnostics(ctx(m=minute.loc[~remove]),15)
    assert m['same_minute_volume_median20'] is None and m['breakout_rvol'] is None
    assert m['opening_range_rvol'] is not None
    remove=(local.dt.date==daily.iloc[-1].timestamp.date())&(local.dt.minute==32)
    m=diagnostics(ctx(m=minute.loc[~remove]),15)
    assert m['opening_range_rvol'] is None and m['breakout_rvol']==2


def test_dst_same_new_york_minute_not_same_utc_minute():
    minute,daily,ctx=history()
    # Fixture crosses the November DST change: local 09:45 remains comparable.
    assert minute.timestamp.dt.hour.nunique()>1
    assert diagnostics(ctx(),15)['same_minute_volume_median20']==105


@pytest.mark.parametrize('key',list(DEFAULTS))
def test_enabled_filter_rejects_missing_data_and_retains_setup(key):
    # Zero width gives unavailable body ratio; all other unavailable histories
    # are checked independently through the filter contract.
    from app.backtesting.strategies.orb_participation import rejection
    assert rejection({**DEFAULTS,key:0},dict.fromkeys(FIELDS)).endswith('_unavailable')


@pytest.mark.parametrize('key,metric,value',[
    ('min_breakout_range_atr','breakout_range_atr',2),('min_breakout_body_ratio','breakout_body_ratio',.5),
    ('min_breakout_rvol','breakout_rvol',2),('min_opening_range_rvol','opening_range_rvol',1),
    ('min_atr_regime_percentile','daily_natr_percentile',50),('max_atr_regime_percentile','daily_natr_percentile',50)])
def test_each_filter_inclusive_boundary_and_rejection(key,metric,value):
    from app.backtesting.strategies.orb_participation import rejection
    params={**DEFAULTS,key:value}
    assert rejection(params,{metric:value}) is None
    bad=value+.01 if key.startswith('max') else value-.01
    assert rejection(params,{metric:bad})==key+'_filter'


def test_zero_volume_missing_whole_session_and_missing_daily_are_unavailable():
    minute,daily,ctx=history()
    local=minute.timestamp.dt.tz_convert('America/New_York')
    day=daily.iloc[-1].timestamp.date()
    assert diagnostics(ctx(m=minute.loc[local.dt.date!=day]),15)['breakout_rvol'] is None
    assert diagnostics(ctx(d=daily.iloc[:-1]),15)['previous_daily_atr14'] is None
    zero=minute.copy();zero.loc[local.dt.date<local.iloc[-1].date(),'volume']=0
    m=diagnostics(ctx(m=zero),15)
    assert m['same_minute_volume_median20']==0 and m['breakout_rvol'] is None
    assert m['opening_range_volume_median20']==0 and m['opening_range_rvol'] is None


def test_service_daily_failure_is_nonfatal_but_enabled_filter_rejects():
    from app.services.backtest import BacktestService
    service=BacktestService(object())
    def load(symbol,timeframe,*args):
        if timeframe=='1d':raise RuntimeError('fixture provider unavailable')
        return orb_frame()
    service._load_timeframe=load
    request=dict(strategy_key='opening_range_breakout_research_v1',symbols=['AAPL'],primary_timeframe='1m',start_date='2026-01-05',end_date='2026-01-05',sizing_mode='quantity',risk_value=1,save_run=False)
    result=service.run(request)
    assert len(result['trades'])==1 and result['trades'][0]['metadata']['previous_daily_atr14'] is None
    assert any('daily history unavailable' in w for w in result['data']['warnings'])
    result=service.run({**request,'strategy_params':{'min_atr_regime_percentile':0}})
    assert not result['trades'] and result['setups'][0]['metadata']['daily_natr_percentile'] is None


def test_defaults_preserve_legacy_research_and_frozen_baseline_executions():
    bars=orb_frame()
    old=simulate(_OpeningRangeResearchRules(),bars);new=simulate(OpeningRangeResearch(),bars)
    def facts(result):
        return [{k:v for k,v in t.items() if k!='metadata'} for t in result['trades']]
    assert facts(old)==facts(new)==facts(simulate(OpeningRangeBreakout(),bars))
    assert OpeningRangeBreakout.spec.defaults==ORB_DEFAULTS
    assert not set(FIELDS)&set(old['trades'][0]['metadata'])
    assert set(FIELDS)<=set(new['setups'][0]['metadata'])
    assert set(FIELDS)<=set(new['trades'][0]['metadata'])


def test_filter_rejection_persisted_and_boundary_inclusive():
    _,_,ctx=history()
    assert OpeningRangeResearch(min_breakout_rvol=2).on_bar(ctx()).rejection_reason is None
    rejected=OpeningRangeResearch(min_breakout_rvol=2.01).on_bar(ctx())
    assert rejected.rejection_reason=='min_breakout_rvol_filter' and rejected.metadata['breakout_rvol']==2
    result=simulate(OpeningRangeResearch(min_breakout_rvol=1),orb_frame())
    assert not result['trades'] and result['setups'][0]['status']=='rejected'
    assert result['setups'][0]['metadata']['breakout_rvol'] is None


@pytest.mark.parametrize('params',[{'min_breakout_rvol':-.1},{'min_breakout_rvol':float('nan')},{'min_breakout_body_ratio':1.1},{'max_atr_regime_percentile':101},{'min_atr_regime_percentile':80,'max_atr_regime_percentile':20}])
def test_invalid_research_thresholds(params):
    with pytest.raises(ValueError):OpeningRangeResearch(**params)


def test_daily_wilder_seed_and_percentile_excludes_latest_reference():
    _,daily,ctx=history();d=daily.copy();d.loc[d.index[-1],'high']=130
    m=diagnostics(ctx(d=d),15)
    assert m['previous_daily_atr14']==pytest.approx((13*4+32)/14)
    assert m['daily_natr_percentile']==100
    assert diagnostics(ctx(d=d.tail(74)),15)['daily_natr_percentile'] is None
    assert wilder_atr(d.iloc[:14])[-1] is None
    d.loc[d.index[-1],'high']=101
    assert diagnostics(ctx(d=d),15)['daily_natr_percentile']==0


def test_diagnostic_warmup_cannot_trade_earlier_or_replace_current_bars():
    minute,daily,ctx=history()
    primary=minute.tail(18).reset_index(drop=True)
    strategy=OpeningRangeResearch()
    strategy.diagnostic_history=minute.copy()  # Deliberately includes future bars.
    signal=strategy.on_bar(ctx(m=primary))
    assert signal.metadata['breakout_rvol']==2
    assert signal.metadata['breakout_range']==4
    assert diagnostics(ctx(m=primary),15)['breakout_rvol'] is None
    with_history=simulate(strategy,primary)
    without_history=simulate(OpeningRangeResearch(),primary)
    assert [t['entry_time'] for t in with_history['trades']]==[t['entry_time'] for t in without_history['trades']]


def test_service_warmup_populates_first_setup_without_extending_execution_period():
    from app.services.backtest import BacktestService
    minute,daily,_=history();primary=minute.tail(18).reset_index(drop=True)
    day=primary.iloc[0].timestamp.tz_convert('America/New_York').date().isoformat()
    service=BacktestService(object())
    def load(symbol,timeframe,start,end,session):
        if timeframe=='1d':return daily
        return minute.iloc[:-18] if end<=primary.iloc[0].timestamp else primary
    service._load_timeframe=load
    result=service.run(dict(strategy_key='opening_range_breakout_research_v1',symbols=['AAPL'],primary_timeframe='1m',start_date=day,end_date=day,sizing_mode='quantity',risk_value=1,save_run=False))
    assert len(result['setups'])==1
    assert result['setups'][0]['metadata']['breakout_rvol']==2
    assert all(pd.Timestamp(t['entry_time'])>=primary.iloc[0].timestamp for t in result['trades'])


def test_new_upper_breakout_and_opening_rvol_bounds_are_exclusive():
    from app.backtesting.strategies.orb_participation import rejection
    metadata=dict.fromkeys(FIELDS)
    metadata['breakout_range_atr']=2
    metadata['opening_range_rvol']=1.25
    params={**DEFAULTS,'max_breakout_range_atr':2,'max_opening_range_rvol':1.25}
    assert rejection(params,metadata)=='max_breakout_range_atr_filter'
    params['max_breakout_range_atr']=2.01
    assert rejection(params,metadata)=='max_opening_range_rvol_filter'
    params['max_opening_range_rvol']=1.26
    assert rejection(params,metadata) is None


def test_research_upper_band_validation_and_disabled_parity():
    with pytest.raises(ValueError,match='minimum < exclusive maximum'):
        OpeningRangeResearch(min_breakout_range_atr=1.5,max_breakout_range_atr=1.5)
    with pytest.raises(ValueError,match='minimum < exclusive maximum'):
        OpeningRangeResearch(min_opening_range_rvol=1,max_opening_range_rvol=.9)
    bars=orb_frame()
    control=simulate(OpeningRangeResearch(),bars)
    explicit_off=simulate(OpeningRangeResearch(max_breakout_range_atr=-1,max_opening_range_rvol=-1),bars)
    assert control['trades']==explicit_off['trades']
