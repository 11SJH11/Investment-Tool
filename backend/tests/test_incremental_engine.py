from copy import deepcopy
from datetime import date
import pandas as pd
import pytest
from app.backtesting.engine import BacktestEngine
from app.backtesting.incremental import IncrementalState
from app.backtesting.models import BacktestConfig, EntrySignal, ExitSignal
from app.backtesting.strategies.base import Strategy, StrategySpec


class Signals(Strategy):
    spec=StrategySpec(key='incremental-fixture',name='Fixture',defaults={},timeframes=('1m',))
    def reset(self):self.calls=[]
    def on_bar(self,ctx):
        self.calls.append(ctx.decision_time.isoformat())
        if ctx.position and len(self.calls)==3:return ExitSignal('fixture_exit')
        if not ctx.position:return EntrySignal('long',90,None,reason='fixture_entry')

def frame():
    return pd.DataFrame(dict(timestamp=pd.date_range('2026-01-02T14:30Z',periods=6,freq='min'),
                             open=[100,101,102,103,104,105],high=[101,102,103,104,105,106],
                             low=[99,100,101,102,103,104],close=[100,101,102,103,104,105],volume=100))

def config():
    return BacktestConfig(sizing_mode='quantity',risk_value=1,allow_overnight=False,
                          commission_per_order=.1,spread_bps=1,slippage_bps=1,max_trades_per_day=3)

def stream():return IncrementalState({date(2026,1,2):pd.Timestamp('2026-01-02T14:36Z').to_pydatetime()})

def execute(engine,strategy,bars,incremental=None):
    return engine.run(symbol_frames={'QQQ':{'1m':bars}},strategies={'QQQ':strategy},
                      primary_timeframe='1m',incremental=incremental)

def test_each_completed_bar_matches_batch_without_premature_flattening():
    engine=BacktestEngine(config());strategy=Signals();state=stream();bars=frame()
    for n in range(1,len(bars)+1):
        actual=execute(engine,strategy,bars.iloc[:n],state)
        assert len(strategy.calls)==n
        if n==1:
            assert state.values['pending_entries'] and not actual['trades']
        if n==2:
            assert state.values['positions'] and not actual['trades']
    expected=execute(BacktestEngine(config()),Signals(),bars)
    assert actual==expected
    assert not state.values['positions']
    assert state.snapshot()['entries_by_day']=={'2026-01-02':2}

def test_duplicate_tick_does_not_repeat_decisions_or_fills():
    engine=BacktestEngine(config());strategy=Signals();state=stream();bars=frame().iloc[:3]
    first=deepcopy(execute(engine,strategy,bars,state))
    assert execute(engine,strategy,bars,state)==first
    assert len(strategy.calls)==3

def test_restart_replay_reconstructs_same_state_and_results():
    bars=frame();first=stream();second=stream();strategy=Signals();other=Signals()
    engine=BacktestEngine(config())
    for n in range(1,5):execute(engine,strategy,bars.iloc[:n],first)
    rebuilt=execute(BacktestEngine(config()),other,bars.iloc[:4],second)
    assert rebuilt==first.result and second.snapshot()==first.snapshot()

def test_unknown_session_and_changed_runtime_fail_closed():
    engine=BacktestEngine(config());strategy=Signals();state=stream();bars=frame()
    with pytest.raises(ValueError,match='session-close'):
        execute(engine,strategy,bars.iloc[:1],IncrementalState({}))
    execute(engine,strategy,bars.iloc[:1],state)
    with pytest.raises(ValueError,match='instance changed'):
        execute(engine,Signals(),bars.iloc[:2],state)

def test_independent_streams_do_not_share_equity_pending_or_strategy_state():
    a,b=stream(),stream();sa,sb=Signals(),Signals()
    execute(BacktestEngine(config()),sa,frame().iloc[:3],a)
    execute(BacktestEngine(config()),sb,frame().iloc[:1],b)
    assert a.values['positions'] and not b.values['positions']
    assert len(sa.calls)==3 and len(sb.calls)==1
    assert a.values['balance']!=b.values['balance']

@pytest.mark.parametrize('key',[
    'vwap_trend_confirmation_quality_research_v5','vwap_d6_mss15_no_opp_fvg15_research_v1',
    'vwap_d6_score4of5_research_v1','vwap_d6_score5of5_research_v1'])
def test_frozen_d6_actual_strategies_match_batch_with_warmup(key):
    import numpy as np
    from app.backtesting.strategies import strategy_registry
    from app.forward.deployments import D6
    from app.services.chart_data import prepare_chart_bars
    if key not in {s.key for s in strategy_registry.specs()}:pytest.skip('Optional local confluence source absent')
    dates=pd.bdate_range('2026-01-02',periods=33)
    stamps=pd.DatetimeIndex([])
    for day in dates:
        part=pd.date_range(str(day.date())+' 14:30',periods=390 if day!=dates[-1] else 30,freq='min',tz='UTC')
        stamps=part if len(stamps)==0 else stamps.append(part)
    x=np.arange(len(stamps));close=100+x*.0002+np.sin(x/4)*.1
    bars=pd.DataFrame(dict(timestamp=stamps,open=close-.03,high=close+.1,low=close-.1,close=close,volume=100+x%390))
    start=stamps[-30];end=stamps[-1]+pd.Timedelta(minutes=1)
    cfg=config();streamed=IncrementalState({start.date():end.to_pydatetime()})
    strategy=strategy_registry.create(key,**D6);engine=BacktestEngine(cfg)
    def frames(f):return {'QQQ':{'1m':f,'15m':prepare_chart_bars(f,'15m','regular')[0]}}
    for n in (10,20,30):
        result=engine.run(symbol_frames=frames(bars.iloc[:len(bars)-30+n]),strategies={'QQQ':strategy},
                          primary_timeframe='1m',evaluation_start=start,incremental=streamed)
    batch=BacktestEngine(cfg).run(symbol_frames=frames(bars),strategies={'QQQ':strategy_registry.create(key,**D6)},
                                primary_timeframe='1m',evaluation_start=start)
    assert result==batch
