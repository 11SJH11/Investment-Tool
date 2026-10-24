import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.forward.deployments import digest
from app.services.algo_decisions import decision_page
from app.storage.database import Database
from tests.test_mt5_t01_runtime import runtime, bars
from tests.test_mt5_t01_runtime import runtime, bars

STREAM='a'*64


def test_real_runtime_decisions_are_read_without_recalculation(runtime):
    runner,identifier,_,_=runtime
    for bar in bars()[:60]:
        runner.step(identifier,bar,observed_at=bar['available_at'],equity=10000.)
    page=decision_page(runner.database,stream_id=identifier,limit=2)
    latest=page['items'][0]
    assert latest['decision_kind']=='entry' and latest['direction']=='short'
    assert latest['stop_loss']==3010 and latest['target_r']==1
    assert page['items'][1]['decision_kind']=='no_signal'
    assert page['next_before']==59
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0]==60
        assert c.execute('SELECT COUNT(*) FROM mt5_execution_attempts').fetchone()[0]==0


def test_empty_legacy_database_is_not_migrated_by_view(tmp_path):
    db=Database(tmp_path/'legacy.db');db.initialize()
    with db.connect() as c:before=c.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
    assert decision_page(db,stream_id=STREAM)==dict(items=[],next_before=None)
    with db.connect() as c:assert c.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()==before


def test_real_runtime_decisions_are_read_without_recalculation(runtime):
    runner,identifier,_,_=runtime
    for bar in bars()[:60]:
        runner.step(identifier,bar,observed_at=bar['available_at'],equity=10000.)
    page=decision_page(runner.database,stream_id=identifier,limit=2)
    latest=page['items'][0]
    assert latest['decision_kind']=='entry' and latest['direction']=='short'
    assert latest['stop_loss']==3010 and latest['target_r']==1
    assert page['items'][1]['decision_kind']=='no_signal'
    assert page['next_before']==59
    with runner.database.connect() as c:
        assert c.execute('SELECT revision FROM mt5_t01_diagnostics').fetchone()[0]==60
        assert c.execute('SELECT COUNT(*) FROM mt5_execution_attempts').fetchone()[0]==0


def test_empty_legacy_database_is_not_migrated_by_view(tmp_path):
    db=Database(tmp_path/'legacy.db');db.initialize()
    with db.connect() as c:before=c.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()
    assert decision_page(db,stream_id=STREAM)==dict(items=[],next_before=None)
    with db.connect() as c:assert c.execute('SELECT name FROM sqlite_master ORDER BY name').fetchall()==before


@pytest.fixture
def db(tmp_path):
    database=Database(tmp_path/'decisions.db');database.initialize()
    with database.connect() as c:
        c.execute('CREATE TABLE mt5_t01_decisions(deployment_id TEXT,sequence INTEGER,document TEXT,sha256 TEXT,PRIMARY KEY(deployment_id,sequence))')
    return database


def add(db, sequence, result=None, stream=STREAM):
    record=dict(decision_at='2026-10-24T01:01:00+00:00',observed_at='2026-10-24T01:01:01+00:00',
                not_before='2026-10-24T01:01:00+00:00',result=result,observation={'secret':'DO_NOT_EXPOSE'},execution_enabled=True)
    with db.connect() as c:
        c.execute('INSERT INTO mt5_t01_decisions VALUES(?,?,?,?)',(stream,sequence,json.dumps(record),digest(record)))


def test_paging_is_per_stream_stable_and_read_only(db):
    for n in range(1,5):add(db,n)
    add(db,999,stream='b'*64)
    first=decision_page(db,stream_id=STREAM,limit=2)
    assert [r['sequence'] for r in first['items']]==[4,3] and first['next_before']==3
    add(db,5)
    second=decision_page(db,stream_id=STREAM,before=3,limit=2)
    assert [r['sequence'] for r in second['items']]==[2,1] and second['next_before'] is None
    assert all(r['decision_kind']=='no_signal' and not r['execution_enabled'] for r in second['items'])
    assert 'DO_NOT_EXPOSE' not in json.dumps(first)
    assert decision_page(db,stream_id='c'*64)['items']==[]
    with db.connect() as c:assert c.execute('SELECT COUNT(*) FROM mt5_t01_decisions').fetchone()[0]==6


@pytest.mark.parametrize('kind',['entry','manage','exit'])
def test_signal_projection_has_no_raw_metadata_or_execution_permission(db,kind):
    add(db,1,dict(kind=kind,signal=dict(direction='short',stop_loss=3010,target_r=1,new_stop_loss=3001,
                                      metadata={'secret':'DO_NOT_EXPOSE'},execution_enabled=True)))
    row=decision_page(db,stream_id=STREAM)['items'][0]
    assert row['decision_kind']==kind and row['integrity']=='checksum_verified'
    assert row['stop_loss']==3010 and row['new_stop_loss']==3001 and row['target_r']==1
    assert not row['execution_enabled'] and 'DO_NOT_EXPOSE' not in json.dumps(row)


def test_corrupt_evidence_is_visible_but_not_presented_as_signal(db):
    add(db,1,dict(kind='entry',signal={}))
    with db.connect() as c:c.execute("UPDATE mt5_t01_decisions SET sha256='broken'")
    row=decision_page(db,stream_id=STREAM)['items'][0]
    assert row['integrity']=='invalid' and row['decision_kind']=='Unavailable'
    assert 'decision_at' not in row


def test_endpoint_bounds_and_no_mutation_route(db):
    from app.api.algo_trading import router
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(database=db)
    with TestClient(app) as client:
        assert client.get('/algo-trading/diagnostic-decisions',params={'stream_id':STREAM}).json()==dict(items=[],next_before=None)
        for values in ({},{'stream_id':'invalid'},{'stream_id':STREAM,'limit':101},{'stream_id':STREAM,'before':0}):
            assert client.get('/algo-trading/diagnostic-decisions',params=values).status_code==422
        assert client.post('/algo-trading/diagnostic-decisions').status_code==405
