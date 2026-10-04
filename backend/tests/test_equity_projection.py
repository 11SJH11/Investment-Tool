from copy import deepcopy
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.backtesting.engine import _decorate_equity_curve, _equity_drawdown

def test_historical_equity_projection_uses_canonical_drawdown_without_mutation(tmp_path):
    db=Database(tmp_path/'saved.db');db.initialize();repo=BacktestRunRepository(db)
    curve=[{'timestamp':f'2024-01-0{i+1}T00:00:00Z','equity':v} for i,v in enumerate([100,120,90,120,130])]
    result={'metrics':{'starting_balance':100,'ending_balance':130,'max_drawdown_pct':-25},'equity_curve':curve}
    saved=repo.create(config={},result=result);before=deepcopy(saved)
    projected=repo.get_section(saved['id'],'summary')['result']['equity_curve']
    assert projected==_decorate_equity_curve(100,curve)
    assert min(p['drawdown_pct'] for p in projected)==_equity_drawdown(100,curve,130)[1]==-25
    assert projected[0]['equity']==100 and projected[-1]['equity']==130
    assert repo.get(saved['id'])==before
