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


def test_settings_copy_never_reads_result_and_preserves_configuration(tmp_path):
    db=Database(tmp_path/'settings.db');db.initialize()
    repo=BacktestRunRepository(db)
    config={'strategy_key':'test','symbols':['QQQ'],'strategy_params':{'length':20},
            'entry_windows':[{'start':'09:30','end':'11:30'}],'risk_value':2.5}
    saved=repo.create(config=config,result={'metrics':{'trades':3000},
        'equity_curve':[{'equity':100}]*10000},name='Original',notes='Keep',tags=['frozen'])
    # Corrupt isolated fixture proves settings never parses the result column.
    with db.connect() as connection:
        connection.execute('UPDATE backtest_runs SET result_json=? WHERE id=?',('not-json',saved['id']))
    settings=repo.get_section(saved['id'],'settings')
    assert settings['config']==config
    assert settings['strategy_key']=='test' and settings['symbols']==['QQQ']
    assert settings['name']=='Original' and settings['notes']=='Keep'
    assert settings['tags']==['frozen'] and settings['result']=={}
    assert len(json.dumps(settings))<2000
    with pytest.raises(ValueError):repo.get_section(999,'settings')


def test_settings_section_api_preserves_config_and_missing_run_status(tmp_path):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api.strategy_lab import backtest_run_section
    db=Database(tmp_path/'api.db');db.initialize()
    repo=BacktestRunRepository(db)
    saved=repo.create(config={'strategy_key':'test','symbols':['QQQ']},result={})
    services=SimpleNamespace(backtest=SimpleNamespace(runs=repo))
    response=backtest_run_section(saved['id'],'settings',services)
    assert response['config']==saved['config'] and response['result']=={}
    with pytest.raises(HTTPException) as error:
        backtest_run_section(999,'settings',services)
    assert error.value.status_code==404
