from copy import deepcopy
from app.storage.equity_display import display_curve
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


def test_display_retains_extrema_events_and_gaps_without_mutation():
    points=[{'timestamp':i,'equity':i%31,'return_pct':i%19,'drawdown_pct':-i%13,'cumulative_r':i%7} for i in range(10000)]
    points[444]['closed_trades']=[{'symbol':'QQQ'}]
    points[555]['realized_pnl']=-10
    points[666]['equity']=None
    original=deepcopy(points);output=display_curve(points)
    indexes={p['timestamp'] for p in output}
    assert {0,9999,444,555,665,666,667}<=indexes
    for key in ('equity','return_pct','drawdown_pct','cumulative_r'):
        assert max(p[key] for p in output if p[key] is not None)==max(p[key] for p in points if p[key] is not None)
        assert min(p[key] for p in output if p[key] is not None)==min(p[key] for p in points if p[key] is not None)
    assert len(output)<3000 and points==original
    assert output==display_curve(points)


def test_progressive_sections_preserve_full_snapshot(tmp_path):
    db=Database(tmp_path/'display.db');db.initialize();repo=BacktestRunRepository(db)
    curve=[dict(timestamp=str(i),equity=100+i,return_pct=i,drawdown_pct=0,cumulative_r=i) for i in range(10000)]
    result={'metrics':{'starting_balance':100,'trades':3000},'equity_curve':curve,'trades':[{'id':i} for i in range(3000)],'analysis':{'n':3000}}
    saved=repo.create(config={'strategy_key':'test'},result=result)
    overview=repo.get_section(saved['id'],'overview')['result']
    assert overview=={'metrics':result['metrics']}
    projected=repo.get_section(saved['id'],'performance')['result']
    assert projected['metrics']==result['metrics']
    assert projected['display_projection']['source_points']==10000
    assert projected['equity_curve']==display_curve(curve)
    assert repo.get_section(saved['id'],'performance-full')['result']['equity_curve']==curve
    assert repo.get(saved['id'])==saved
