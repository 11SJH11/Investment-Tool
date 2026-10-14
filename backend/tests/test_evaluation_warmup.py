import pandas as pd
import pytest
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig,EntrySignal
from app.backtesting.strategies.base import Strategy,StrategySpec


class WarmupStrategy(Strategy):
    spec=StrategySpec(key='warmup_fixture',name='Warmup fixture',timeframes=('1m',))
    def reset(self):self.observations=[]
    def on_bar(self,ctx):
        self.observations.append((ctx.decision_time,len(ctx.bars())))
        if len(self.observations)==1:
            return EntrySignal('long',90,take_profit=120)


def run(start=None):
    bars=pd.DataFrame({'timestamp':pd.date_range('2026-01-02T14:30Z',periods=10,freq='min'),
        'open':100.,'high':101.,'low':99.,'close':100.,'volume':100})
    strategy=WarmupStrategy()
    result=BacktestEngine(BacktestConfig(sizing_mode='quantity',risk_value=1)).run(
        symbol_frames={'QQQ':{'1m':bars}},strategies={'QQQ':strategy},primary_timeframe='1m',evaluation_start=start)
    return result,strategy


def test_warmup_is_visible_but_never_generates_signals_fills_or_equity():
    start=pd.Timestamp('2026-01-02T14:35Z')
    result,strategy=run(start)
    assert len(strategy.observations)==5
    assert strategy.observations[0]==(pd.Timestamp('2026-01-02T14:36Z').to_pydatetime(),6)
    assert result['trades'][0]['entry_time']=='2026-01-02T14:36:00+00:00'
    assert all(pd.Timestamp(p['timestamp'])>=start for p in result['equity_curve'])


def test_explicit_beginning_equals_default_engine_results_exactly():
    assert run()[0]==run(pd.Timestamp('2026-01-02T14:30Z'))[0]


def test_warmup_rejects_ambiguous_timezone_and_empty_evaluation():
    with pytest.raises(ValueError,match='timezone'):run(pd.Timestamp('2026-01-02T14:35'))
    with pytest.raises(ValueError,match='No primary'):run(pd.Timestamp('2026-01-03T14:35Z'))


def test_full_period_limits_require_explicit_authority_and_stay_bounded():
    from app.research_agent.sandbox_runs import Approval,ACK,check_input_limits
    from app.research_agent.sandbox import SandboxError
    request=dict(control_parameters={},candidate_parameters={},acknowledgement=ACK,timeout_seconds=601)
    with pytest.raises(ValueError,match='600-second'):Approval(**request)
    assert Approval(**request,full_period=True).timeout_seconds==601
    with pytest.raises(ValueError):Approval(**{**request,'timeout_seconds':21601},full_period=True)
    data={'symbols':['QQQ'],'frames_by_symbol':{'QQQ':{'1m':pd.DataFrame({'close':range(10001)})}}}
    with pytest.raises(SandboxError,match='10000'):check_input_limits(data)
    check_input_limits(data,full_period=True)
    data['symbols'].append('SPY')
    with pytest.raises(SandboxError,match='SINGLE_SYMBOL'):check_input_limits(data,full_period=True)
