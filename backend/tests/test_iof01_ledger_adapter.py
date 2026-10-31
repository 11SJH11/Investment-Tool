"""Self-contained adapter equivalence tests (no Ledger installation required)."""
from __future__ import annotations
import importlib.util
import sys
import types
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' if (ROOT / 'backend/tools').is_dir() else ROOT
SOURCE = BACKEND / 'tools/iof01_reference_backtest.py'
PLUGIN = BACKEND / 'app/backtesting/strategies/iof01_displacement_ledger_v1.py'


def load_source():
    spec = importlib.util.spec_from_file_location('iof01_reference_backtest_test', SOURCE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_plugin(monkeypatch):
    for name in ('app','app.backtesting','app.backtesting.strategies'):
        m=types.ModuleType(name)
        m.__path__=[]
        monkeypatch.setitem(sys.modules,name,m)
    for name in ('app.backtesting.context','app.backtesting.models','app.backtesting.strategies.base','app.backtesting.strategies.registry'):
        monkeypatch.setitem(sys.modules,name,types.ModuleType(name))
    class StrategyContext:pass
    @dataclass
    class EntrySignal:
        direction:str
        stop_loss:float
        take_profit:float|None=None
        reason:str=''
        metadata:dict=field(default_factory=dict)
        order_type:str='market'
        entry_price:float|None=None
        max_wait_bars:int|None=None
        target_r:float|None=None
    @dataclass
    class ExitSignal:reason:str='strategy_exit'
    @dataclass
    class ManagePositionSignal:
        new_stop_loss:float|None=None
        new_take_profit:float|None=None
        reduce_fraction:float|None=None
        reason:str=''
        metadata:dict=field(default_factory=dict)
    @dataclass
    class ParameterSpec:
        key:str
        label:str
        kind:str
        default:object
        minimum:float|None=None
        maximum:float|None=None
        step:float|None=None
    @dataclass
    class StrategySpec:
        key:str
        name:str
        description:str=''
        defaults:dict=field(default_factory=dict)
        category:str=''
        timeframes:tuple=('1m',)
        parameters:tuple=()
        risk_management:dict=field(default_factory=dict)
        source_file:str=''
    class Strategy:
        def __init__(self,**params):self.params={**self.spec.defaults,**params}
    class Registry:
        items=[]
        def register(self, cls):self.items.append(cls);return cls
    registry=Registry()
    sys.modules['app.backtesting.context'].StrategyContext=StrategyContext
    sys.modules['app.backtesting.models'].EntrySignal=EntrySignal
    sys.modules['app.backtesting.models'].ExitSignal=ExitSignal
    sys.modules['app.backtesting.models'].ManagePositionSignal=ManagePositionSignal
    sys.modules['app.backtesting.strategies.base'].ParameterSpec=ParameterSpec
    sys.modules['app.backtesting.strategies.base'].Strategy=Strategy
    sys.modules['app.backtesting.strategies.base'].StrategySpec=StrategySpec
    sys.modules['app.backtesting.strategies.registry'].strategy_registry=registry
    spec=importlib.util.spec_from_file_location('iof01_ledger_test',PLUGIN)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod,registry


def frame(n=300):
    rng=np.random.default_rng(888)
    jumps=rng.normal(0,0.30,n)
    # Clear bidirectional impulses to exercise candidate discovery paths.
    for at,val in [(65,3.3),(98,-3.9),(146,4.5),(183,-3.4),(235,3.8)]:
        jumps[at]=val
    closes=100+np.cumsum(jumps)
    opens=np.r_[100,closes[:-1]]
    high=np.maximum(opens,closes)+rng.uniform(0.01,0.15,n)
    low=np.minimum(opens,closes)-rng.uniform(0.01,0.15,n)
    return pd.DataFrame({'timestamp':pd.date_range('2025-04-01',periods=n,freq='min',tz='UTC'),
                         'open':opens,'high':high,'low':low,'close':closes})


@pytest.mark.parametrize('variant',['basic','bos','bos_fvg'])
def test_candidate_matches_reference_across_sliding_window(monkeypatch,variant):
    source=load_source();plugin,_=load_plugin(monkeypatch)
    config=source.Settings(variant=variant)
    prepared=source.prepare(frame(),config)
    candidate_count=0
    for i in range(72,len(prepared)):
        original=source.make_candidate(prepared,i,config,1)
        local=prepared.iloc[max(0,i-71):i+1].reset_index(drop=True)
        expected=plugin.make_candidate(local,len(local)-1,plugin.DetectorSettings(variant=variant),1)
        assert (original is None)==(expected is None), f'{variant} index {i}'
        if original:
            candidate_count+=1
            for attr in ('direction','zone_low','zone_high','entry','initial_stop','atr',
                         'impulse_bars','displacement_in_atr','bos','fvg'):
                assert getattr(original,attr)==pytest.approx(getattr(expected,attr))
            assert prepared.at[original.base_i,'timestamp']==local.at[expected.base_i,'timestamp']
    assert candidate_count>0


def test_running_atr_equals_source_prior_atr(monkeypatch):
    source=load_source();plugin,_=load_plugin(monkeypatch)
    ref=source.prepare(frame(),source.Settings())
    strategy=plugin.Iof01BasicLedgerV1();strategy.reset()
    for i,row in ref.iterrows():
        got=strategy._update_atr(row)
        expect=ref.at[i,'atr_previous']
        if pd.isna(expect):assert got is None
        else:assert got==pytest.approx(expect,rel=1e-12)


def test_three_registry_classes_registered(monkeypatch):
    plugin,registry=load_plugin(monkeypatch)
    assert {item.spec.key for item in registry.items}=={
        'iof01_basic_ledger_v1','iof01_bos_ledger_v1','iof01_bos_fvg_ledger_v1'}
    for cls in registry.items:
        x=cls();x.reset()
        assert x.spec.timeframes==('1m',)


def test_native_limit_signal_on_bullish_impulse(monkeypatch):
    plugin,_=load_plugin(monkeypatch)
    df=frame()
    class Ctx:
        primary_timeframe='1m'
        position=None
        def __init__(self,i):self.i=i
        def bars(self,tf,count):return df.iloc[max(0,self.i-count+1):self.i+1].copy()
    strat=plugin.Iof01BasicLedgerV1();strat.reset()
    signals=[]
    for i in range(len(df)):
        result=strat.on_bar(Ctx(i))
        if result is not None:signals.append(result)
    assert signals
    for s in signals:
        assert s.order_type=='limit'
        assert s.target_r==3.0
        assert s.max_wait_bars==90
        assert s.stop_loss<s.entry_price if s.direction=='long' else s.stop_loss>s.entry_price


def test_native_partial_flags_apply_next_open(monkeypatch):
    plugin,_=load_plugin(monkeypatch)
    strategy=plugin.Iof01BosLedgerV1();strategy.reset();strategy._active_since=10;strategy._bar_count=12
    pos=types.SimpleNamespace(direction='long',entry_price=100.,initial_risk_per_share=2.,
            metadata={'iof01_version':'ledger_single_entry_v1','iof01_reference_variant':'bos'})
    m=strategy._manage(None,pos,pd.Series({'high':102.5,'low':100.2}))
    assert m.reduce_fraction==pytest.approx(.3)
    pos.metadata.update(m.metadata)
    m2=strategy._manage(None,pos,pd.Series({'high':104.5,'low':101.2}))
    assert m2.reduce_fraction==pytest.approx(3/7)
    assert m2.new_stop_loss==100.


@pytest.mark.parametrize('variant',['basic','bos','bos_fvg'])
def test_source_reference_still_runs_and_has_outputs(variant):
    source=load_source()
    df=frame(300).rename(columns={'timestamp':'time'})
    result, signals,trades,parts=source.run_backtest(df,source.Settings(variant=variant))
    assert result['bars']==300
    assert {'signals','filled_campaigns','total_r'}.issubset(result)
    assert 'variant' in signals.columns or signals.empty


def test_original_source_default_is_two_entries():
    assert load_source().Settings().max_entries==2
