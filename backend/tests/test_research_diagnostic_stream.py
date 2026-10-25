import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.research_agent import event_diagnostics as d
from tests.test_research_campaigns import repo,create


def test_cursor_retention_and_restart(repo,monkeypatch):
    campaign=create(repo)
    monkeypatch.setattr(d,'MAX_CAMPAIGN_EVENTS',3)
    with repo.database.connect() as c:
        for n in range(6):d.append(c,campaign['id'],component='research.campaign',operation='fixture',status='completed')
    first=d.page(repo.database,campaign['id'],limit=2)
    assert len(first['items'])==2 and first['has_more']
    second=d.page(repo.database,campaign['id'],first['next_after'])
    assert len(second['items'])==1 and not second['has_more']
    assert not d.page(repo.database,campaign['id'],second['next_after'])['items']


def test_private_trace_never_appears_in_public_event(repo):
    campaign=create(repo)
    try:raise ValueError('Bearer SECRET /secret/path SELECT * FROM holdout')
    except ValueError as exc:trace=d.private_trace(exc)
    assert 'SECRET' not in json.dumps(trace)
    with repo.database.connect() as c:
        d.append(c,campaign['id'],component='research.model',operation='validation',status='failed',error='unknown_evidence_reference',trace=trace)
        assert c.execute('SELECT private_trace FROM agent_diagnostics WHERE private_trace IS NOT NULL').fetchone()
    public=json.dumps(d.page(repo.database,campaign['id']))
    assert 'private_trace' not in public and 'SECRET' not in public
    assert 'UNKNOWN_EVIDENCE_REFERENCE' in public


def test_event_and_state_rollback_together(repo):
    campaign=create(repo)
    before=d.page(repo.database,campaign['id'])['next_after']
    with pytest.raises(RuntimeError):
        with repo.database.connect() as c:
            d.append(c,campaign['id'],component='research.test',operation='rollback',status='started')
            raise RuntimeError('rollback')
    assert not d.page(repo.database,campaign['id'],before)['items']


def test_authenticated_endpoint_no_mutation_or_secret_echo(repo):
    from app.api.research_campaigns import router
    campaign=create(repo);token='private-test-token-'*3
    app=FastAPI();app.state.services=SimpleNamespace(database=repo.database,settings=SimpleNamespace(research_diagnostics_token=token))
    app.include_router(router)
    path=f"/strategy-lab/research-campaigns/{campaign['id']}/diagnostics"
    with TestClient(app) as client:
        assert client.get(path).status_code==401
        assert client.get(path,headers={'Authorization':'Bearer wrong'}).status_code==401
        response=client.get(path,headers={'Authorization':'Bearer '+token})
        assert response.status_code==200 and token not in response.text
        assert client.get(path+'?after=-1',headers={'Authorization':'Bearer '+token}).status_code==422
        app.state.services.settings.research_diagnostics_token=''
        assert client.get(path).status_code==503


def test_cross_campaign_isolation_and_private_unknown_error(repo):
    one=create(repo);other=repo.create(dict(request_key='other',mode='FIND_STRATEGIES'))
    with repo.database.connect() as c:
        d.append(c,other['id'],component='research.model',operation='call',status='failed',error='API_KEY=secret')
    assert all(row['campaign_id']==one['id'] for row in d.page(repo.database,one['id'])['items'])
    assert 'secret' not in json.dumps(d.page(repo.database,other['id']))


def test_independent_catalog_family_rejection_is_explicit(repo):
    from app.research_agent.discovery import queue
    item=create(repo);request=item['request'];request['policy']['symbols']=['XAUUSD']
    rejected=[];chosen=queue(request,rejections=rejected)
    assert any(row['family_id']=='opening_range' for row in rejected)
    assert any(row['family_id']=='vwap_continuation' for row in chosen)
    request['policy']['budget']['families']=1
    rejected=[];assert len(queue(request,rejections=rejected))==1
    assert not rejected
