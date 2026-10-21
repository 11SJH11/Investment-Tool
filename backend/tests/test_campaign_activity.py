import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_research_campaigns import repo, create
from app.api.research_campaigns import router, repository


def seed(repo, identifier, count):
    with repo.database.connect() as c:
        for i in range(count):
            repo._event(c, identifier, 'FIXTURE_EVENT', {'index': i})


def test_bounded_cursor_preserves_history_during_new_inserts(repo):
    item = create(repo)
    seed(repo, item['id'], 125)
    first = repo.activity(item['id'])
    assert len(first['items']) == 50
    expected = first['items'][0]['id']
    seed(repo, item['id'], 3)
    found = first['items'][:]
    page = first
    while page['next_before']:
        page = repo.activity(item['id'], before=page['next_before'])
        found.extend(page['items'])
    assert len(found) == 126  # includes CREATED
    assert [r['id'] for r in found] == list(range(expected, 0, -1))
    assert len(repo.report(item['id'])['events']) == 50
    with repo.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM agent_campaign_events').fetchone()[0] == 129


def test_activity_isolated_by_campaign_and_unknown_rejected(repo):
    first = create(repo)
    second = repo.create(dict(request_key='second',mode='FIND_STRATEGIES'))
    seed(repo, second['id'], 5)
    assert all(r['campaign_id'] == first['id'] for r in repo.activity(first['id'])['items'])
    with pytest.raises(ValueError, match='Unknown'):
        repo.activity('missing')


@pytest.mark.parametrize('kwargs',[{'limit':0},{'limit':101},{'limit':True},{'before':0},{'before':-1},{'before':True}])
def test_invalid_activity_bounds(repo, kwargs):
    with pytest.raises(ValueError):
        repo.activity(create(repo)['id'], **kwargs)


def test_activity_api_bounds_and_cursor(repo):
    item = create(repo);seed(repo,item['id'],3)
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[repository]=lambda:repo
    with TestClient(app) as client:
        path=f"/strategy-lab/research-campaigns/{item['id']}/activity"
        response=client.get(path+'?limit=2')
        assert response.status_code == 200
        page=response.json()
        assert len(page['items']) == 2
        second=client.get(path+f"?before={page['next_before']}&limit=2").json()
        assert second['next_before'] is None
        assert not ({r['id'] for r in page['items']} & {r['id'] for r in second['items']})
        assert client.get(path+'?limit=101').status_code == 422
        assert client.get(path+'?before=-1').status_code == 422
