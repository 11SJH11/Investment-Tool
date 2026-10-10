from copy import deepcopy
import pytest
from app.research_agent.quarantine import inspect_source,store
from app.backtesting.strategies import strategy_registry
from tests.test_research_trials import research
from tests.test_research_validation import frozen


def payload(source):return dict(request_key='one',registry_key='research_child_fixture',source=source,rationale='Fixture only',acknowledgement='Store this source as an inert quarantined draft; no execution or activation')


def test_parser_does_not_claim_safety_or_echo_syntax_source():
    report=inspect_source('raise RuntimeError("secret")')
    assert report['syntax_valid'] and report['safe_to_execute'] is False
    broken=inspect_source('secret-string =')
    assert not broken['syntax_valid'] and 'secret-string' not in str(broken)


def test_quarantine_never_executes_registers_or_enqueues(frozen,tmp_path):
    (db,_,project,_,jobs,_),candidate=frozen
    marker=tmp_path/'must-not-exist'
    source=f"from pathlib import Path\nPath({str(marker)!r}).write_text('unsafe')\n"
    before=deepcopy(strategy_registry.specs());count=len(jobs.list())
    result=store(db,project['id'],candidate['id'],payload(source))
    assert result['state']=='QUARANTINED' and result['execution_enabled'] is False
    assert not marker.exists() and strategy_registry.specs()==before and len(jobs.list())==count
    assert 'source' not in result['request']
    assert store(db,project['id'],candidate['id'],payload(source))==result
    with pytest.raises(ValueError,match='immutable'):store(db,project['id'],candidate['id'],payload('pass'))
    changed=payload(source);changed['request_key']='two'
    with pytest.raises(ValueError,match='unique'):store(db,project['id'],candidate['id'],changed)



def test_quarantine_api_requires_consent_exports_verified_bytes_and_has_no_run_action(frozen):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from app.api.research_agent import router
    (db,_,project,_,_,_),candidate=frozen
    app=FastAPI();app.include_router(router);app.state.services=SimpleNamespace(database=db)
    url=f"/strategy-lab/research-agent/{project['id']}/candidates/{candidate['id']}/code-drafts"
    with TestClient(app) as client:
        data=payload('raise SystemExit(1)')
        assert client.post(url,json={k:v for k,v in data.items() if k!='acknowledgement'}).status_code==422
        saved=client.post(url,json=data);assert saved.status_code==200
        identifier=saved.json()['id']
        assert len(client.get(url).json()['items'])==1
        assert client.get(url+'/'+identifier+'/source').json()['source']==data['source']
        assert client.post(url+'/'+identifier+'/run',json={}).status_code==404
        with db.connect() as c:c.execute("UPDATE agent_code_drafts SET source='changed'")
        assert client.get(url+'/'+identifier+'/source').status_code==400
