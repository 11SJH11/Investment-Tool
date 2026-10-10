from copy import deepcopy
from app.storage.reproducibility import export_manifest,environment_snapshot
from app.research_agent.analysis import digest
from tests.test_strategy_source_archive import repository


def test_legacy_manifest_never_substitutes_current_environment(repository,monkeypatch):
    monkeypatch.setattr('app.storage.reproducibility.environment_snapshot',lambda:(_ for _ in ()).throw(AssertionError('No current lookup')))
    run=repository.create(config={'symbols':['QQQ'],'notes':'private','api_key':'secret'},result={})
    result=export_manifest(repository.database,run['id'])
    assert result['execution_environment'] is None and result['replayable_archive'] is False
    assert 'api_key' not in result['configuration'] and 'notes' not in result['configuration']
    assert result==export_manifest(repository.database,run['id'])


def test_manifest_preserves_recorded_environment_and_input_identity(repository):
    env={'python':'old fixture','packages':{'pandas':'fixture'}}
    run=repository.create(config={'market_data_fingerprint':'recorded','strategy_params':{'threshold':2}},result={'execution_environment':env,'trades':[]})
    before=deepcopy(repository.get(run['id']))
    result=export_manifest(repository.database,run['id'])
    assert result['execution_environment']==env and result['market_data_fingerprint']=='recorded'
    checksum=result.pop('manifest_sha256');assert digest(result)==checksum
    assert repository.get(run['id'])==before


def test_environment_snapshot_contains_no_user_paths_or_environment(monkeypatch):
    monkeypatch.setenv('BROKER_SECRET_SENTINEL','do-not-export')
    env=environment_snapshot()
    assert set(env)=={'python','implementation','system','machine','packages','scope'}
    assert set(env['packages'])=={'pandas','numpy','pydantic','duckdb'}
    assert 'do-not-export' not in str(env)



def test_manifest_api_exports_recorded_data_only(repository):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.strategy_lab import router
    run=repository.create(config={},result={})
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(backtest=SimpleNamespace(runs=repository))
    with TestClient(app) as client:
        response=client.get('/strategy-lab/runs/'+str(run['id'])+'/reproducibility')
        assert response.status_code==200 and response.json()['execution_environment'] is None
        assert client.get('/strategy-lab/runs/999/reproducibility').status_code==404
