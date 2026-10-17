import pytest
from app.forward.metrics import summarize, deployment_metrics
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running, minutes


def test_hand_worked_metrics_and_marked_drawdown():
    trades=[dict(net_pnl=20,r_multiple=2,direction='long',exit_reason='session_close'),
            dict(net_pnl=-10,r_multiple=-1,direction='short'),dict(net_pnl=0,r_multiple=None,direction='long')]
    result=summarize(trades,100,110,[('2026-01-02T15:00Z',120),('2026-01-02T16:00Z',90),('2026-01-05T15:00Z',110)])
    assert result['n']==3 and result['r_sample_size']==2 and result['observed_sessions']==2
    assert (result['wins'],result['losses'],result['breakeven'])==(1,1,1)
    assert result['win_rate_pct']==pytest.approx(100/3)
    assert result['profit_factor']==2 and result['total_r']==1 and result['average_r']==.5
    assert result['return_pct']==pytest.approx(10)
    assert result['max_drawdown_cash']==30 and result['max_drawdown_pct']==25
    assert result['long_profit_factor'] is None and result['short_profit_factor']==0
    assert result['average_winner']==20 and result['largest_loser']==-10
    assert result['session_close_winners']==1 and result['low_sample']


def test_empty_sample_and_timezone_session_count():
    empty=summarize([],100,100,[])
    assert empty['n']==0 and empty['profit_factor'] is None and empty['average_r'] is None
    assert empty['max_drawdown_pct'] is None and empty['win_rate_pct'] is None
    observed=summarize([],100,100,[('2026-01-02T23:59Z',100),('2026-01-03T00:01Z',100)])
    assert observed['observed_sessions']==1


def test_runtime_metrics_use_all_closed_trades_and_read_only_checkpoint_equity(running):
    runtime,experiment,_=running
    rows=runtime.ingest(experiment,minutes(6))
    with runtime.database.connect() as c:
        for row in rows:
            metrics=deployment_metrics(c,row)
            assert metrics['n']==len(row['state']['trade_history'])
            assert metrics['observed_sessions']==1
            assert metrics['max_drawdown_cash']>=0
    assert runtime.deployments.list(experiment)==rows
