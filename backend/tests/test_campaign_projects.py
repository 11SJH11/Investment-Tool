from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import json

import pytest

from tests.test_research_campaigns import repo, coverage, create
from tests.test_research_foundation import saved
from app.backtesting.strategies import strategy_registry
from app.research_agent.campaign_projects import provision
from app.research_agent.repository import ResearchRepository
from app.research_agent.access import scope, check


def ready(repo):
    campaign = create(repo)
    # Families intentionally share a trusted strategy in this storage fixture.
    key = strategy_registry.specs()[0].key
    campaign = repo.prepare(campaign['id'], [dict(family_id=f, strategy_key=key, reason='Independent research family')
                                            for f in ['one', 'two']], [coverage()])
    return campaign


def bounds(day):
    start = datetime.combine(datetime.fromisoformat(day).date(), time.min, tzinfo=ZoneInfo('America/New_York'))
    return start, start + timedelta(days=1)


def test_provision_is_atomic_idempotent_and_shares_exact_dataset_ids(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    assert links == provision(repo.database, campaign['id'])
    assert links[0]['dataset_ids'] == links[1]['dataset_ids']
    with repo.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM agent_projects').fetchone()[0] == 2
        assert c.execute('SELECT COUNT(*) FROM agent_datasets').fetchone()[0] == 2
        assert c.execute('SELECT COUNT(*) FROM agent_dataset_memberships').fetchone()[0] == 4
    registry = ResearchRepository(repo.database)
    assert registry.get(links[0]['project_id'])['datasets'] == registry.get(links[1]['project_id'])['datasets']


def test_holdout_consumption_is_global_and_never_development_access(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    registry = ResearchRepository(repo.database)
    first, second = [registry.get(x['project_id']) for x in links]
    held = next(d for d in second['datasets'] if d['state'] == 'LOCKED_HOLDOUT')
    dev = next(d for d in second['datasets'] if d['state'] == 'DEVELOPMENT')
    for p in [first, second]:
        with scope(repo.database, p['id']):
            check('QQQ', '1m', *bounds(dev['start']))
            with pytest.raises(ValueError, match='Holdout'): check('QQQ', '1m', *bounds(held['start']))
    registry.approve_holdout(second['id'], held['id'], 'This dataset will no longer be unseen')
    assert next(d for d in registry.get(first['id'])['datasets'] if d['id'] == held['id'])['state'] == 'INSPECTED_VALIDATION'
    with pytest.raises(ValueError, match='locked holdout'):
        registry.approve_holdout(first['id'], held['id'], 'This dataset will no longer be unseen')
    for p in [first, second]:
        with scope(repo.database, p['id']):
            with pytest.raises(ValueError, match='outside declared'): check('QQQ', '1m', *bounds(held['start']))
    assert provision(repo.database, campaign['id']) == links
    assert next(d for d in registry.get(first['id'])['datasets'] if d['id'] == held['id'])['state'] == 'INSPECTED_VALIDATION'


def test_consumed_holdout_results_cannot_enter_campaign_development_analysis(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    registry = ResearchRepository(repo.database)
    project = registry.get(links[1]['project_id'])
    held = next(d for d in project['datasets'] if d['state'] == 'LOCKED_HOLDOUT')
    registry.approve_holdout(project['id'], held['id'], 'This dataset will no longer be unseen')
    run = saved(repo.database, project['strategy_key'], held['start'])
    with pytest.raises(ValueError, match='consumed validation'): registry.inspect_run(project['id'], run['id'])
    assert registry.get(project['id'])['analyses'] == {}


def test_another_project_cannot_claim_shared_records(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    registry = ResearchRepository(repo.database)
    other = registry.create('Outside', strategy_registry.specs()[0].key, [dict(
        start='2010-01-01', end='2010-12-31', symbols=['QQQ'], timeframe='1m', state='DEVELOPMENT')])
    held = next(d for d in registry.get(links[0]['project_id'])['datasets'] if d['state'] == 'LOCKED_HOLDOUT')
    assert held['id'] not in {d['id'] for d in other['datasets']}
    with pytest.raises(ValueError): registry.approve_holdout(other['id'], held['id'], 'This dataset will no longer be unseen')


def test_exposure_after_planning_rolls_back_all_provisioning(repo):
    campaign = ready(repo)
    held = campaign['plans']['QQQ:1m']['holdout']
    saved(repo.database, strategy_registry.specs()[0].key, held['start'])
    with pytest.raises(ValueError, match='inspected since planning'): provision(repo.database, campaign['id'])
    with repo.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM agent_projects').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM agent_datasets').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM agent_dataset_memberships').fetchone()[0] == 0
    assert not repo.get(campaign['id']).get('projects')


def test_plan_tampering_rejected(repo):
    campaign = ready(repo)
    campaign['plans']['QQQ:1m']['development']['end'] = '2025-01-01'
    with repo.database.connect() as c: repo._save(c, campaign)
    with pytest.raises(ValueError, match='integrity'): provision(repo.database, campaign['id'])


def test_deleted_shared_dataset_is_not_recreated(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    with repo.database.connect() as c:
        c.execute('DELETE FROM agent_datasets WHERE id=?', (links[0]['dataset_ids'][0],))
    with pytest.raises(ValueError, match='no automatic recreation'): provision(repo.database, campaign['id'])


def test_shared_development_can_be_inspected_normally(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    registry = ResearchRepository(repo.database)
    project = registry.get(links[1]['project_id'])
    day = campaign['plans']['QQQ:1m']['development']['start']
    run = saved(repo.database, project['strategy_key'], day)
    inspected = registry.inspect_run(project['id'], run['id'])
    assert inspected['baseline_run_id'] == run['id']
    assert inspected['research_debt']['uses'] == 1
