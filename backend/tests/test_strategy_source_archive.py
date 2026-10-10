import base64
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
import pytest
from app.backtesting.strategies import strategy_registry
from app.storage.strategy_source_archive import export_run, manifest_for
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database
from tests.test_strategy_refresh import directory, source
from tests.test_research_infrastructure import services, base


def test_captured_bytes_survive_disk_edit_refresh_and_preserve_saved_runs(directory,tmp_path):
    path=directory/'refresh_fixture.py';original=source().encode();path.write_bytes(original)
    assert strategy_registry.refresh()['ok']
    service,_,_=services(tmp_path/'store');payload={**base(),'strategy_key':'refresh_fixture','save_run':True}
    # Disk is newer than the loaded implementation. Capture must use loaded bytes.
    path.write_text(source(value=2),encoding='utf-8')
    first=service.run(payload);rid=first['saved_run']['id'];saved=deepcopy(service.get_run(rid))
    bundle=export_run(service.runs.database,rid)
    assert base64.b64decode(bundle['files']['refresh_fixture.py'])==original
    assert first['strategy']['source_archive']['status']=='archived'
    assert first['execution_environment']['packages']['pandas']
    assert saved['result']['execution_environment']==first['execution_environment']
    assert bundle['archive']['module_sha256']==sha256(original).hexdigest()
    with service.runs.database.connect() as c:count=c.execute('SELECT COUNT(*) FROM strategy_source_blobs').fetchone()[0]
    assert strategy_registry.refresh()['ok']
    second=service.run(payload);new=export_run(service.runs.database,second['saved_run']['id'])
    assert new['archive']['sha256']!=bundle['archive']['sha256']
    assert service.get_run(rid)==saved and export_run(service.runs.database,rid)==bundle
    with service.runs.database.connect() as c:assert c.execute('SELECT COUNT(*) FROM strategy_source_blobs').fetchone()[0]==count+1


@pytest.fixture
def repository(tmp_path):
    db=Database(tmp_path/'db');db.initialize();return BacktestRunRepository(db)


def save(repository,sources):
    manifest,identifier=manifest_for(sources)
    result={'strategy':{'key':'fixture','implementation':{'module':'app.backtesting.strategies.fixture','source_sha256':manifest['fixture.py'],'registry_sha256':identifier}}}
    return repository.create(config={'symbols':['QQQ']},result=result,strategy_sources=sources)


def test_archive_deduplicates_and_round_trips_exact_non_utf8_bytes(repository):
    sources={'fixture.py':b'# coding: latin-1\n# \xe9\r\n'}
    a=save(repository,sources);b=save(repository,sources)
    assert a['result']['strategy']['source_archive']==b['result']['strategy']['source_archive']
    assert base64.b64decode(export_run(repository.database,a['id'])['files']['fixture.py'])==sources['fixture.py']
    with repository.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM strategy_source_blobs').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM strategy_source_archives').fetchone()[0]==1


def test_mismatched_capture_cannot_create_saved_run(repository):
    with pytest.raises(ValueError,match='differs from executed'):
        repository.create(config={},result={'strategy':{'implementation':{'module':'x.fixture','source_sha256':'wrong','registry_sha256':'wrong'}}},strategy_sources={'fixture.py':b'pass'})
    assert repository.list()==[]


@pytest.mark.parametrize('filename',['../fixture.py','C:fixture.py','folder/fixture.py','folder\\fixture.py','fixture.txt'])
def test_archive_rejects_unsafe_paths(filename):
    with pytest.raises(ValueError,match='module or bytes'):manifest_for({filename:b'pass'})


def test_legacy_runs_are_not_backfilled_from_current_source(repository,monkeypatch):
    old=repository.create(config={},result={'strategy':{'implementation':{'source_sha256':'old'}}})
    monkeypatch.setattr(strategy_registry,'sources',lambda:pytest.fail('Must not read current registry'))
    with pytest.raises(ValueError,match='No captured source archive'):export_run(repository.database,old['id'])
    assert repository.get(old['id'])==old


def test_corrupted_archive_is_detected_and_never_executed(repository):
    run=save(repository,{'fixture.py':b'raise RuntimeError("Must never execute")'})
    with repository.database.connect() as c:c.execute('UPDATE strategy_source_blobs SET content=?',(b'corrupt',))
    with pytest.raises(ValueError,match='integrity'):export_run(repository.database,run['id'])
    with pytest.raises(ValueError,match='integrity'):save(repository,{'fixture.py':b'raise RuntimeError("Must never execute")'})
    assert len(repository.list())==1


def test_source_export_api_is_explicit_and_legacy_unavailable(repository):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.strategy_lab import router
    from app.api.dependencies import get_services
    run=save(repository,{'fixture.py':b'# source fixture'})
    legacy=repository.create(config={},result={})
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=SimpleNamespace(runs=repository))
    with TestClient(app) as client:
        r=client.get(f"/strategy-lab/runs/{run['id']}/source-archive")
        assert r.status_code==200 and r.json()['encoding']=='base64'
        assert client.get(f"/strategy-lab/runs/{legacy['id']}/source-archive").status_code==404
        assert client.get('/strategy-lab/runs/999999/source-archive').status_code==404
    assert 'files' not in repository.get(run['id'])['result']['strategy']['source_archive']


def test_concurrent_saves_share_one_archive_atomically(repository):
    from concurrent.futures import ThreadPoolExecutor
    sources={'fixture.py':b'# concurrent capture'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs=list(pool.map(lambda _:save(repository,sources),range(8)))
    assert len({r['id'] for r in runs})==8
    assert len({r['result']['strategy']['source_archive']['sha256'] for r in runs})==1
    with repository.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM strategy_source_blobs').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM strategy_source_archives').fetchone()[0]==1
