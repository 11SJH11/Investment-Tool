import json
import pytest
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository

def test_sections_preserve_snapshot_and_exclude_heavy_payloads(tmp_path):
    db=Database(tmp_path/'runs.db');db.initialize()
    repo=BacktestRunRepository(db)
    result={'strategy':{'key':'test'},'metrics':{'trades':1000},'equity_curve':[{'equity':100}], 'trades':[{'metadata':{'evidence':'x'*500}}]*1000,'analysis':{'large':[1]*100},'setups':[{'status':'rejected'}],'rejected_signals':[{'reason':'test'}]}
    saved=repo.create(config={'strategy_key':'test'},result=result)
    summary=repo.get_section(saved['id'],'summary')
    assert 'trades' not in summary['result'] and 'analysis' not in summary['result']
    assert summary['result']['equity_curve']==result['equity_curve']
    assert len(json.dumps(summary))<len(json.dumps(saved))/20
    assert repo.get_section(saved['id'],'trades')['result']['trades']==result['trades']
    assert repo.get_section(saved['id'],'analysis')['result']['analysis']==result['analysis']
    assert repo.get(saved['id'])==saved
    with pytest.raises(ValueError):repo.get_section(saved['id'],'invalid')
    with pytest.raises(ValueError):repo.get_section(999,'summary')
