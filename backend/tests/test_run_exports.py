from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZipFile
from types import SimpleNamespace as NS

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api.strategy_lab import router
from app.services.run_exports import export_files, research_pack, zip_files, csv_bytes, ResearchPack
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


@pytest.fixture
def repository(tmp_path):
    db=Database(tmp_path/'db');db.initialize()
    return BacktestRunRepository(db)


def test_versioned_pack_bundle_checksums_and_snapshot_immutability(repository):
    run=repository.create(config={'strategy_key':'fixture'},result={'metrics':{'trades':1},
        'trades':[{'symbol':'NASUSD','direction':'long','entry_time':'2026-01-01T10:00Z',
                   'exit_time':'2026-01-01T10:01Z','r_multiple':1,'net_pnl':2,'metadata':{'spread_at_entry':.1}}],
        'analysis':{'breakdowns':{'symbol':[{'symbol':'NASUSD','trades':1}]}}})
    files=export_files(repository,run['id'])
    pack=ResearchPack.model_validate_json(files['research-pack.json'])
    assert pack.format=='ledger.research_pack.v1' and pack.experiment_contract is None
    assert pack.availability['microstructure']=='UNAVAILABLE'
    assert pack.research_analysis['summary']['n']==1
    manifest=json.loads(files['manifest.json'])
    assert all(sha256(files[name]).hexdigest()==entry['sha256'] for name,entry in manifest['files'].items())
    archive=zip_files(files)
    assert archive==zip_files(export_files(repository,run['id']))
    with ZipFile(BytesIO(archive)) as zip:
        assert set(zip.namelist())==set(files)
        assert b'spread_at_entry' in zip.read('trades.csv')
    assert repository.get(run['id'])==run
    assert all(not name.endswith('.parquet') for name in files)


def test_missing_trade_evidence_does_not_invent_zero_trades(repository):
    run=repository.create(config={},result={})
    pack,_=research_pack(repository,run['id'])
    assert pack['research_analysis'] is None and pack['metrics'] is None
    assert pack['availability']['trades']=='UNAVAILABLE'
    assert 'trades.csv' not in export_files(repository,run['id'])


def test_csv_formula_safety_and_numeric_losses():
    text=csv_bytes([{'symbol':'=HYPERLINK("bad")','pnl':-4,'note':'@sum(1)'}]).decode('utf-8-sig')
    assert "'=HYPERLINK" in text and "'@sum" in text and '-4' in text


def test_export_api_and_unsupported_format(repository):
    run=repository.create(config={},result={'trades':[]})
    app=FastAPI();app.include_router(router)
    app.state.services=NS(backtest=NS(runs=repository))
    with TestClient(app) as client:
        response=client.get(f'/strategy-lab/runs/{run["id"]}/export')
        assert response.status_code==200 and response.headers['content-type']=='application/zip'
        assert response.content[:2]==b'PK'
        assert client.get(f'/strategy-lab/runs/{run["id"]}/export?kind=pack').json()['format']=='ledger.research_pack.v1'
        assert client.get(f'/strategy-lab/runs/{run["id"]}/export?kind=../../other').status_code==422
        assert client.get('/strategy-lab/runs/999/export').status_code==400


def test_selected_bundle_has_separate_runs_and_no_inferred_winner(repository):
    from app.services.run_exports import selected_export
    a=repository.create(config={},result={'trades':[]})
    b=repository.create(config={},result={'trades':[]})
    content=selected_export(repository,[b['id'],a['id'],a['id']])
    with ZipFile(BytesIO(content)) as archive:
        assert f'run-{a["id"]}/trades.csv' in archive.namelist()
        assert f'run-{b["id"]}/research-pack.json' in archive.namelist()
        evidence=json.loads(archive.read('comparison-evidence.json'))
        assert [r['run_id'] for r in evidence['runs']]==[a['id'],b['id']]
        assert 'winner' not in evidence
        manifest=json.loads(archive.read('bundle-manifest.json'))
        assert all(sha256(archive.read(name)).hexdigest()==entry['sha256'] for name,entry in manifest['files'].items())
    with pytest.raises(ValueError):selected_export(repository,[])
    with pytest.raises(ValueError):selected_export(repository,[a['id'],999])


def test_selected_export_budget_and_api(repository, monkeypatch):
    from app.services.run_exports import selected_export
    a=repository.create(config={},result={})
    monkeypatch.setattr('app.services.run_exports.MAX_EXPORT_BYTES',1)
    with pytest.raises(ValueError, match='budget'):
        selected_export(repository,[a['id']])
