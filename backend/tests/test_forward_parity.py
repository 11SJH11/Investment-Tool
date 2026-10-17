import pytest
from app.forward.parity import SessionParity
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running,minutes


def test_independent_session_replay_matches_and_preserves_live_state(running):
    runtime,experiment,_=running
    before=runtime.ingest(experiment,minutes(6))
    identities={k:id(v[1]) for k,v in runtime.instances.items()}
    report=SessionParity(runtime).run(experiment,'2026-01-02')
    assert report['status']=='PASS' and len(report['results'])==4
    assert all(all(r['checks'].values()) for r in report['results'])
    assert runtime.deployments.list(experiment)==before
    assert identities=={k:id(v[1]) for k,v in runtime.instances.items()}
    with runtime.database.connect() as c:assert SessionParity(runtime).reports(c,experiment)[0]==report


def test_session_replay_exposes_corrupt_checkpoint(running):
    runtime,experiment,_=running
    runtime.ingest(experiment,minutes(6))
    with runtime.database.connect() as c:c.execute("UPDATE forward_checkpoints SET sha256='corrupt'")
    assert SessionParity(runtime).run(experiment,'2026-01-02')['status']=='FAIL'


def test_incomplete_session_and_changed_source_cannot_pass(running):
    runtime,experiment,registry=running
    runtime.ingest(experiment,minutes(2))
    with pytest.raises(ValueError,match='close bar'):SessionParity(runtime).run(experiment,'2026-01-02')
    runtime.ingest(experiment,minutes(6))
    registry.content['fixture.py']=b'# changed'
    with pytest.raises(ValueError,match='changed'):SessionParity(runtime).run(experiment,'2026-01-02')


def test_changed_recorded_setup_path_is_a_visible_failure(running):
    import json
    from app.forward.deployments import digest
    runtime,experiment,_=running
    runtime.ingest(experiment,minutes(6))
    with runtime.database.connect() as c:
        row=c.execute('SELECT deployment_id,decision_at,evidence_json FROM forward_checkpoints ORDER BY decision_at DESC LIMIT 1').fetchone()
        evidence=json.loads(row[2]);evidence['setup_sha256']='different-eligibility-path'
        c.execute('UPDATE forward_checkpoints SET evidence_json=?,sha256=? WHERE deployment_id=? AND decision_at=?',
                  (json.dumps(evidence),digest(evidence),row[0],row[1]))
    result=SessionParity(runtime).run(experiment,'2026-01-02')
    failed=next(r for r in result['results'] if r['status']=='FAIL')
    assert not failed['checks']['setup_sha256'] and failed['checks']['trade_sha256']


def test_parity_api_contract(running):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.forward import router,service
    runtime,experiment,_=running
    runtime.ingest(experiment,minutes(6))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[service]=lambda:SimpleNamespace(parity=SessionParity(runtime))
    with TestClient(app) as client:
        assert client.post(f'/forward/{experiment}/parity',json={'session_date':'2026-01-02'}).json()['status']=='PASS'
        assert client.post(f'/forward/{experiment}/parity',json={'session_date':'2026-01-03'}).status_code==400
        assert client.post(f'/forward/{experiment}/parity',json={'session_date':'bad'}).status_code==422
