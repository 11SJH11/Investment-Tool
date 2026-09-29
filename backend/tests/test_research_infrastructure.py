from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import time

import pandas as pd
import pytest

from app.backtesting.context import StrategyContext, completion_indexes
from app.backtesting.strategies.base import ParameterSpec
from app.backtesting.strategies.intraday_baselines import ORB_RESEARCH
from app.frame_cache import FrameCache, frames
from app.performance import Profile
from app.services.research_experiments import axis_values, children, preview
from app.services.backtest import BacktestService
from app.services.market_data import MarketDataService
from app.services.chart_data import prepare_chart_bars, _prepare_chart_bars
from app.storage.database import Database
from app.storage.market_store import MarketStore
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.backtest_run_repository import BacktestRunRepository
from tests.test_intraday_baselines import orb_frame


SPEC = ParameterSpec('x','X','float',-1,minimum=-1,maximum=5,step=.25)


@pytest.mark.parametrize('axis,expected', [
    ({'mode':'range','start':'0','end':'1.5','step':'.25'},[0,.25,.5,.75,1,1.25,1.5]),
    ({'mode':'range','start':'0','end':'1','count':5},[0,.25,.5,.75,1]),
    ({'values':'-1, 0, 1.5'},[-1,0,1.5]),
])
def test_decimal_generation(axis, expected):
    got=axis_values(axis,SPEC,25)
    assert got['values']==expected
    assert not any('999999' in v for v in got['labels'])


@pytest.mark.parametrize('axis',[
    {'values':'NaN'}, {'values':'0,0'}, {'values':'-2'}, {'values':'6'}, {'values':'.1'},
    {'mode':'range','start':1,'end':0,'step':1}, {'mode':'range','start':0,'end':1,'step':0},
    {'mode':'range','start':0,'end':1,'step':-.1}, {'mode':'range','start':0,'end':1,'count':3.5},
    {'mode':'range','start':0,'end':1,'count':3,'step':.5},
    {'mode':'range','start':0,'end':1,'count':26}, {'mode':'range','start':0,'end':1,'count':4},
    {'values':[]}, {'values':list(range(26))},
])
def test_invalid_values_are_rejected_not_truncated(axis):
    with pytest.raises(ValueError):axis_values(axis,SPEC,25)


def test_integer_values_and_default_sentinel():
    integer=replace(SPEC,kind='int',step=1)
    assert axis_values({'mode':'range','start':0,'end':3,'step':1},integer,25)['values']==[0,1,2,3]
    with pytest.raises(ValueError):axis_values({'values':'.5'},integer,25)
    assert axis_values({'values':'-1'},replace(SPEC,step=.3),25)['values']==[-1]
    assert len(axis_values({'mode':'range','start':-1,'end':5,'step':.25},SPEC,25)['values'])==25


def base():
    return dict(strategy_key=ORB_RESEARCH,symbols=['SPY'],primary_timeframe='1m',session='regular',
                start_date='2026-01-05',end_date='2026-01-05',starting_balance=1e6,
                sizing_mode='quantity',risk_value=1,allow_overnight=False,strategy_params={})


def axes():
    return [dict(parameter='min_breakout_body_ratio',values='-1,0.5'),
            dict(parameter='min_breakout_range_atr',values='-1,1')]


def test_cartesian_immutable_group_and_size():
    original=base();before=deepcopy(original)
    plan,runs=children(original,axes(),'key','Hypothesis','Notes',['tag'],'validation')
    assert plan['cells']==[[-1,-1],[-1,1],[.5,-1],[.5,1]]
    assert len(runs)==4 and {r['experiment_group'] for r in runs}=={'research:key'}
    assert [r['research_experiment']['cell_index'] for r in runs]==list(range(4))
    runs[0]['strategy_params']['mutated']=1
    assert original==before and 'mutated' not in runs[1]['strategy_params']
    with pytest.raises(ValueError):preview(original,[axes()[0],axes()[0]])
    with pytest.raises(ValueError):preview({**original,'symbols':['SPY','QQQ']},axes())
    with pytest.raises(ValueError):preview(original,[dict(parameter='min_breakout_range_atr',values=list(range(9))),axes()[0]])


class Provider:
    key='fixture';cache_namespace='research-test-raw-v1'
    def __init__(self):self.calls=0;self.frame=orb_frame()
    def get_bars(self,symbol,tf,start,end):
        self.calls+=1
        return self.frame.loc[(self.frame.timestamp>=start)&(self.frame.timestamp<=end)].copy()


def services(tmp_path):
    db=Database(tmp_path/'isolated.db');db.initialize()
    p=Provider();store=MarketStore(tmp_path/'market')
    market=MarketDataService(p,store,MarketCacheRepository(db))
    return BacktestService(market,BacktestRunRepository(db)),market,p


def facts(result):
    return {k:result[k] for k in ('trades','metrics','setups','analysis','equity_curve')}


def test_cold_warm_grid_standalone_and_concurrent_exact_parity(tmp_path):
    frames.clear();service,market,p=services(tmp_path)
    original=base();cold=service.run(original);calls=p.calls
    with Profile() as profile:warm=service.run(original)
    assert p.calls==calls and facts(cold)==facts(warm)
    assert profile.counts.get('parquet_physical_read',0)==0
    _,runs=children(original,axes(),'parity')
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(service.run,runs))
    for run,result in zip(runs,results):
        standalone=service.run({**original,'strategy_params':run['strategy_params']})
        assert facts(result)==facts(standalone)
        saved=service.get_run(result['saved_run']['id'])
        assert saved['config']['research_experiment']==run['research_experiment']
    assert len(service.get_experiment('research:parity')['runs'])==4
    assert original==base()


@pytest.mark.parametrize('count',[None,0,1,3,100,-1])
@pytest.mark.parametrize('available',[False,True])
def test_indexed_context_identical_and_copy_safe(count,available):
    f=orb_frame()
    if available:f['available_at']=f.timestamp+pd.Timedelta(minutes=3)
    kwargs=dict(symbol='SPY',primary_timeframe='1m',decision_time=f.iloc[10].timestamp+pd.Timedelta(seconds=45),
                frames={'1m':f},position=None,equity=1e6)
    a=StrategyContext(**kwargs)
    b=StrategyContext(**kwargs,completion_indexes=completion_indexes(kwargs['frames']))
    pd.testing.assert_frame_equal(a.bars(count=count),b.bars(count=count))
    copied=b.bars();copied.loc[:,'close']=999
    assert f.close.iloc[0]==100
    f.loc[15:,'close']=9999 # future mutation cannot leak through the boundary
    pd.testing.assert_frame_equal(a.bars(count=count),b.bars(count=count))


def test_nonmonotonic_completion_falls_back():
    f=orb_frame();f['available_at']=f.timestamp+pd.Timedelta(minutes=1)
    f.loc[0,'available_at']=f.timestamp.iloc[-1]
    kw=dict(symbol='SPY',primary_timeframe='1m',decision_time=f.iloc[8].timestamp,frames={'1m':f},position=None,equity=1)
    pd.testing.assert_frame_equal(StrategyContext(**kw).bars(),StrategyContext(**kw,completion_indexes=completion_indexes(kw['frames'])).bars())


def test_lru_ttl_memory_and_copies():
    f=orb_frame();c=FrameCache(max_entries=2,ttl=.01)
    c.put('a',f);copy=c.get('a');copy.loc[:,'close']=999
    pd.testing.assert_frame_equal(c.get('a'),f)
    c.put('b',f);c.get('a');c.put('c',f)
    assert c.get('b') is None
    time.sleep(.02);assert c.get('a') is None
    tiny=FrameCache(max_bytes=1);tiny.put('x',f);assert tiny.get('x') is None
    c.clear();assert c.stats()['approx_bytes']==0


def test_range_cache_refresh_namespace_and_sessions(tmp_path):
    frames.clear();service,market,p=services(tmp_path)
    start=p.frame.timestamp.iloc[0].to_pydatetime();end=(p.frame.timestamp.iloc[-1]+pd.Timedelta(minutes=1)).to_pydatetime()
    whole=market.get_bars('SPY','1m',start,end);calls=p.calls
    subset=market.get_bars('SPY','1m',start+pd.Timedelta(minutes=5),end)
    pd.testing.assert_frame_equal(subset,whole.iloc[5:].reset_index(drop=True))
    assert p.calls==calls
    p.frame['volume']=999
    refreshed=market.get_bars('SPY','1m',start,end,force_refresh=True)
    assert refreshed.volume.eq(999).all() and p.calls==calls+1
    p.cache_namespace='research-test-other';p.frame['volume']=888
    assert market.get_bars('SPY','1m',start,end).volume.eq(888).all()
    for session in ('regular','extended','24h'):
        for tf in ('1m','5m','1h'):
            expected,method=_prepare_chart_bars(whole,tf,session)
            actual,label=prepare_chart_bars(whole,tf,session)
            pd.testing.assert_frame_equal(actual,expected)
            pd.testing.assert_frame_equal(prepare_chart_bars(whole,tf,session)[0],expected)
            assert label==method


def test_exact_band_generation_sets_paired_max_and_nonoverlapping_semantics():
    original=base()
    axis={'parameter':'min_breakout_range_atr','mode':'bands','values':'1,1.25,1.5,1.75,2'}
    plan,runs=children(original,[axis],'bands','ATR bands')
    assert plan['job_count']==4
    generated=plan['axes'][0]
    assert generated['upper_parameter']=='max_breakout_range_atr'
    assert generated['bands']==[[1.0,1.25],[1.25,1.5],[1.5,1.75],[1.75,2.0]]
    assert generated['labels']==['1–1.25','1.25–1.5','1.5–1.75','1.75–2']
    assert generated['bound_semantics']=='[lower, upper)'
    assert [r['strategy_params']['min_breakout_range_atr'] for r in runs]==[1.0,1.25,1.5,1.75]
    assert [r['strategy_params']['max_breakout_range_atr'] for r in runs]==[1.25,1.5,1.75,2.0]
    assert all(r['research_experiment']['cell_overrides']['max_breakout_range_atr'] == r['strategy_params']['max_breakout_range_atr'] for r in runs)
    assert original==base()


def test_generated_band_count_is_number_of_intervals_not_edges():
    plan=preview(base(),[{'parameter':'min_breakout_range_atr','mode':'bands','start':1,'end':2,'count':4}])
    assert plan['job_count']==4
    assert plan['axes'][0]['bands']==[[1.0,1.25],[1.25,1.5],[1.5,1.75],[1.75,2.0]]


def test_band_mode_rejects_unpaired_parameter_and_effective_axis_collision():
    with pytest.raises(ValueError,match='no paired maximum'):
        preview(base(),[{'parameter':'min_breakout_body_ratio','mode':'bands','values':'0,.5,1'}])
    with pytest.raises(ValueError,match='same effective parameter'):
        preview(base(),[
            {'parameter':'min_breakout_range_atr','mode':'bands','values':'1,1.5,2'},
            {'parameter':'max_breakout_range_atr','values':'1.75,2.25'},
        ])
