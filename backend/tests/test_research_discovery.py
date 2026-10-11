from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from app.research_agent.discovery import cached_coverage, prepare, queue
from app.research_agent.campaign_projects import provision
from app.research_agent.repository import ResearchRepository
from app.storage.market_store import MarketStore
from tests.test_research_campaigns import repo, create


def market(tmp_path, timestamps):
    store = MarketStore(tmp_path/'cache')
    frame = pd.DataFrame(dict(timestamp=timestamps, open=1, high=2, low=1, close=2, volume=10))
    store.write_bars('fixture', 'QQQ', '1m', frame)
    return SimpleNamespace(store=store, provider_for=lambda symbol: SimpleNamespace(cache_namespace='fixture'))


def test_timestamp_only_coverage_excludes_current_and_future_dates(tmp_path):
    data = market(tmp_path, pd.to_datetime(['2024-03-08T15:00Z', '2024-03-11T14:00Z', '2024-03-12T14:00Z', '2030-01-01T15:00Z']))
    coverage = cached_coverage(data, 'QQQ', '1m', now=datetime(2024,3,12,23,tzinfo=timezone.utc))
    assert [d.isoformat() for d in coverage.sessions] == ['2024-03-08', '2024-03-11']
    assert coverage.provider_namespace == 'fixture'
    # Price revisions cannot influence selection or timestamp identity.
    bars = data.store.read_bars('fixture', 'QQQ', '1m')
    bars['close'] = 999
    data.store.replace_bars('fixture', 'QQQ', '1m', bars)
    assert cached_coverage(data, 'QQQ', '1m', now=datetime(2024,3,12,23,tzinfo=timezone.utc)) == coverage


def test_no_weekday_invention_or_timezone_date_shift(tmp_path):
    data = market(tmp_path, pd.to_datetime(['2024-03-09T00:30Z', '2024-03-12T00:30Z']))
    result = cached_coverage(data,'QQQ','1m',now=datetime(2024,3,12,1,tzinfo=timezone.utc))
    assert [d.isoformat() for d in result.sessions] == ['2024-03-08']


@pytest.mark.parametrize('symbol,timeframe', [('NQ1!','1m'),('../secret','1m'),('QQQ','../1m')])
def test_unsupported_identity_fails_closed(tmp_path, symbol, timeframe):
    data = market(tmp_path, pd.date_range('2020-01-01',periods=3,tz='UTC'))
    with pytest.raises(ValueError): cached_coverage(data,symbol,timeframe)


def test_missing_and_corrupt_history_do_not_fabricate_dates(tmp_path):
    data = market(tmp_path, pd.date_range('2020-01-01',periods=3,tz='UTC'))
    with pytest.raises(ValueError,match='unavailable'): cached_coverage(data,'SPY','1m')
    data.store._path('fixture','QQQ','1m').write_bytes(b'bad')
    with pytest.raises(ValueError,match='unreadable'): cached_coverage(data,'QQQ','1m')


def test_automatic_prepare_idempotence_and_provider_binding(repo, tmp_path):
    item = create(repo)
    data = market(tmp_path, pd.date_range('2020-01-01T15:00Z',periods=800,freq='B'))
    services = SimpleNamespace(database=repo.database,market_data=data)
    result = prepare(services,item['id'])
    assert result == prepare(services,item['id'])
    assert result['discovery']['provider_calls'] == 0
    assert len({e['family_id'] for e in result['queue']}) == len(result['queue'])
    links = provision(repo.database,item['id'])
    assert ResearchRepository(repo.database).get(links[0]['project_id'])['provider_bindings'] == {'QQQ:1m':'fixture'}


def test_novel_idea_not_replaced_with_unrelated_catalog_strategy(repo):
    item = repo.create(dict(request_key='idea',mode='RESEARCH_IDEA',prompt='A novel structural idea'))
    with pytest.raises(ValueError,match='Code Author'): queue(item['request'])


def test_insufficient_cache_keeps_campaign_draft(repo,tmp_path):
    item=create(repo)
    data=market(tmp_path,pd.date_range('2020-01-01',periods=5,tz='UTC'))
    with pytest.raises(ValueError,match='Insufficient'):
        prepare(SimpleNamespace(database=repo.database,market_data=data),item['id'])
    assert repo.get(item['id'])['status']=='DRAFT'


def test_provider_change_is_blocked_before_loading_prices(repo,tmp_path):
    from app.research_agent.access import scope, check
    from tests.test_campaign_projects import bounds
    item=create(repo)
    data=market(tmp_path,pd.date_range('2020-01-01T15:00Z',periods=800,freq='B'))
    result=prepare(SimpleNamespace(database=repo.database,market_data=data),item['id'])
    link=provision(repo.database,item['id'])[0]
    day=result['plans']['QQQ:1m']['development']['start']
    with scope(repo.database,link['project_id']):
        with pytest.raises(ValueError,match='namespace changed'):
            check('QQQ','1m',*bounds(day),namespace='other-feed')


def test_auto_prepare_api_and_no_order_actions(repo,tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.dependencies import get_services
    from app.api.research_campaigns import router
    app=FastAPI()
    app.include_router(router)
    data=market(tmp_path,pd.date_range('2020-01-01T15:00Z',periods=800,freq='B'))
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(database=repo.database,market_data=data)
    item=create(repo)
    with TestClient(app) as client:
        response=client.post('/strategy-lab/research-campaigns/'+item['id']+'/auto-prepare')
        assert response.status_code==200,response.text
        assert response.json()['status']=='PREPARED'
        assert client.post('/strategy-lab/research-campaigns/'+item['id']+'/place-order').status_code==422


def test_bounded_coverage_never_silently_truncates(tmp_path,monkeypatch):
    data=market(tmp_path,pd.date_range('2020-01-01',periods=5,tz='UTC'))
    monkeypatch.setattr('app.research_agent.discovery.MAX_COVERAGE_ROWS',3)
    with pytest.raises(ValueError,match='bounded'):cached_coverage(data,'QQQ','1m')
