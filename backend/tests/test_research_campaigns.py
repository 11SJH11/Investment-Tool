"""Campaign planning/control-plane tests: no model, provider or Docker calls."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json

import pytest

from app.backtesting.strategies import strategy_registry
from app.research_agent.campaign_policy import CampaignPolicy, preset
from app.research_agent.campaigns import Campaigns
from app.research_agent.dataset_planner import SessionCoverage, known_exposure, plan
from app.research_agent.repository import ResearchRepository
from app.storage.database import Database
from tests.test_research_foundation import saved


def coverage(symbol='QQQ'):
    # Explicit synthetic completed sessions, not a claim about an exchange calendar.
    dates = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(800)]
    return dict(symbol=symbol, timeframe='1m', provider_namespace='fixture:v1',
                source_fingerprint='synthetic-fixture', completed_through=dates[-1], sessions=dates)


@pytest.fixture
def repo(tmp_path):
    db = Database(tmp_path/'campaigns.db')
    db.initialize()
    return Campaigns(db, clock=lambda: datetime(2026, 10, 10, tzinfo=timezone.utc))


def create(repo, **changes):
    return repo.create(dict(request_key='request', mode='FIND_STRATEGIES', **changes))


def prepare(repo, item):
    key = strategy_registry.specs()[0].key
    return repo.prepare(item['id'], [dict(family_id='family', strategy_key=key, reason='Fixture family; not a performance claim')], [coverage()])


def active(repo):
    # Execution integration intentionally absent at this checkpoint. Exercise its
    # internal reservation gate without exposing an unsafe public Start action.
    item = prepare(repo, create(repo, policy=CampaignPolicy(send_development_summaries=True).model_dump()))
    item.update(status='ACTIVE', deadline='2026-10-11T00:00:00+00:00')
    with repo.database.connect() as c:
        repo._save(c, item)
    return item


def decision(**changes):
    return dict(request_key='action1', action='RUN_PARAMETER_EXPERIMENT', family_id='family',
                reason='Test a preregistered numerical hypothesis', challenge='Could destroy winners',
                resources=dict(simulations=2, hypotheses=1), **changes)


def test_deterministic_chronological_plan_without_performance_input():
    a = plan(coverage())
    assert a == plan(coverage())
    assert a['warmup']['sessions'] == 250
    assert a['development']['sessions'] == 385
    assert a['holdout']['sessions'] == 165
    assert a['warmup']['end'] < a['development']['start'] < a['development']['end'] < a['holdout']['start']
    windows = a['internal_development_windows']
    assert sum(w['sessions'] for w in windows) == 385
    assert all(x['end'] < y['start'] for x, y in zip(windows, windows[1:]))
    assert a['holdout']['state'] == 'PROPOSED_UNSEEN'
    assert a['future_oos'] is None
    assert a['dataset_proposal'][0]['start'] == a['warmup']['start']


@pytest.mark.parametrize('change', ['duplicate', 'unordered', 'future', 'short', 'invalid_symbol'])
def test_invalid_session_manifest_fails(change):
    raw = coverage()
    if change == 'duplicate': raw['sessions'].append(raw['sessions'][-1])
    if change == 'unordered': raw['sessions'].reverse()
    if change == 'future': raw['completed_through'] = raw['sessions'][-2]
    if change == 'short': raw['sessions'] = raw['sessions'][:300]
    if change == 'invalid_symbol': raw['symbol'] = ' '
    with pytest.raises(ValueError): plan(raw)


@pytest.mark.parametrize('kind', ['SAVED_RUN', 'INSPECTED', 'INSPECTED_VALIDATION', 'LOCKED_HOLDOUT', 'FUTURE_OOS', 'DEVELOPMENT'])
def test_exposure_never_moves_dates_or_fabricates_unseen_holdout(kind):
    expected = plan(coverage())
    held = expected['holdout']
    result = plan(coverage(), exposure=[dict(start=held['start'], end=held['start'], kind=kind, reference='prior')])
    assert result['development'] == expected['development']
    assert result['holdout']['start'] == held['start']
    assert result['holdout']['state'] == 'UNAVAILABLE'
    assert len(result['dataset_proposal']) == 1


@pytest.mark.parametrize('kind', ['LOCKED_HOLDOUT', 'FUTURE_OOS'])
def test_protected_warmup_or_development_cannot_be_used(kind):
    with pytest.raises(ValueError, match='protected'):
        plan(coverage(), exposure=[dict(start='2020-01-01', end='2020-01-02', kind=kind)])


def test_exposure_uses_saved_scope_and_futures_family(repo):
    key = strategy_registry.specs()[0].key
    saved(repo.database, key, '2021-12-01')
    assert known_exposure(repo.database, 'QQQ')[0]['kind'] == 'SAVED_RUN'
    ResearchRepository(repo.database).create('Other project', key, [dict(start='2021-01-01', end='2021-02-01',
        symbols=['NQ1!'], timeframe='1m', state='LOCKED_HOLDOUT')])
    assert known_exposure(repo.database, 'NQH25')[0]['kind'] == 'LOCKED_HOLDOUT'


def test_default_policy_is_versioned_and_retry_survives_changed_defaults(repo):
    item = create(repo)
    updated = repo.defaults()
    updated['budget']['simulations'] = 42
    repo.defaults(updated)
    assert create(repo) == item
    assert repo.create(dict(request_key='new', mode='FIND_STRATEGIES'))['request']['policy']['budget']['simulations'] == 42
    assert item['request']['policy']['budget']['simulations'] == 240


@pytest.mark.parametrize('name,minutes', [('QUICK', 60), ('STANDARD', 1440), ('DEEP', 2880)])
def test_presets_have_explicit_bounded_authority(name, minutes):
    policy = preset(name)
    assert policy.budget.wall_minutes == minutes
    assert not policy.code_generation and not policy.external_research
    assert policy.holdout == 'human_approval'


@pytest.mark.parametrize('bad', [dict(code_generation=True), dict(external_research=True),
                                dict(budget={'llm_usd': float('nan')}), dict(docker_args=['--privileged'])])
def test_policy_rejects_missing_authority_and_unknown_execution_controls(bad):
    with pytest.raises(ValueError): CampaignPolicy.model_validate(bad)


def test_request_key_and_plan_are_immutable(repo):
    item = create(repo)
    with pytest.raises(ValueError, match='immutable'): create(repo, prompt='Different goal')
    item = prepare(repo, item)
    assert item['status'] == 'PREPARED'
    with pytest.raises(ValueError, match='frozen'): prepare(repo, item)
    assert Campaigns(repo.database).get(item['id'])['plan_hash'] == item['plan_hash']
    report = repo.report(item['id'])
    assert not report['summary']['execution_available']
    assert not report['summary']['holdout_consumed_by_campaign']
    assert [e['action'] for e in report['events']] == ['CREATED', 'PLAN_FROZEN']


def test_preparing_plan_does_not_mutate_global_data_registry_or_run_jobs(repo):
    ResearchRepository(repo.database)
    item = prepare(repo, create(repo))
    with repo.database.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM agent_datasets').fetchone()[0] == 0
        assert c.execute('SELECT COUNT(*) FROM backtest_runs').fetchone()[0] == 0
    assert item['reserved']['simulations'] == 0


def test_current_session_coverage_rejected(repo):
    item = create(repo)
    raw = coverage()
    raw['completed_through'] = '2026-10-10'
    with pytest.raises(ValueError, match='current UTC'):
        repo.prepare(item['id'], [dict(family_id='a', strategy_key=strategy_registry.specs()[0].key, reason='Test')], [raw])


def test_missing_policy_symbol_coverage_rejected(repo):
    item = create(repo, policy=CampaignPolicy(symbols=['QQQ', 'SPY']).model_dump())
    with pytest.raises(ValueError, match='every policy'): prepare(repo, item)


@pytest.mark.parametrize('mode', ['IMPROVE_STRATEGY', 'RESEARCH_IDEA'])
def test_mode_requires_necessary_input(repo, mode):
    with pytest.raises(ValueError): repo.create(dict(request_key='r', mode=mode))


def test_cancel_idempotent_and_cannot_start_unintegrated_dispatcher(repo):
    item = create(repo)
    result = repo.transition(item['id'], 'cancel')
    assert result == repo.transition(item['id'], 'cancel')
    with pytest.raises(ValueError): repo.transition(item['id'], 'start')
    with pytest.raises(ValueError): repo.transition(item['id'], 'resume')


def test_reservation_is_atomic_idempotent_and_restart_safe(repo):
    item = active(repo)
    a = repo.reserve(item['id'], decision())
    assert repo.reserve(item['id'], decision()) == a
    restarted = Campaigns(repo.database, clock=repo.clock)
    assert restarted.reserve(item['id'], decision()) == a
    assert restarted.get(item['id'])['reserved']['simulations'] == 2
    different = decision(); different['reason'] = 'Changed'
    with pytest.raises(ValueError, match='immutable'): repo.reserve(item['id'], different)
    second = decision(); second['request_key'] = 'second'
    with pytest.raises(ValueError, match='Reconcile'): repo.reserve(item['id'], second)


@pytest.mark.parametrize('action', ['GENERATE_CHILD_STRATEGY', 'EXTERNAL_RESEARCH', 'VALIDATE_CANDIDATE'])
def test_decision_cannot_escalate_authority(repo, action):
    item = active(repo)
    d = decision(); d['action'] = action
    with pytest.raises(ValueError): repo.reserve(item['id'], d)
    assert repo.get(item['id'])['reserved']['simulations'] == 0


def test_overspend_rejected_before_action_persistence(repo):
    item = active(repo)
    d = decision(); d['resources']['simulations'] = 241
    with pytest.raises(ValueError, match='budget exhausted'): repo.reserve(item['id'], d)
    assert repo.report(item['id'])['actions'] == []


@pytest.mark.parametrize('command', ['pause', 'stop_after_current', 'cancel'])
def test_control_commands_block_new_reservations(repo, command):
    item = active(repo)
    repo.transition(item['id'], command)
    with pytest.raises(ValueError, match='inactive'): repo.reserve(item['id'], decision())


def test_elapsed_deadline_cannot_be_reset_by_restart(repo):
    item = active(repo)
    restarted = Campaigns(repo.database, clock=lambda: datetime(2026, 10, 12, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match='wall-clock'): restarted.reserve(item['id'], decision())
    assert restarted.get(item['id'])['deadline'] == item['deadline']
