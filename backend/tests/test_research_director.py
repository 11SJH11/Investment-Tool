from datetime import timedelta
from threading import Event
from types import SimpleNamespace
import json

import pytest

from tests.test_research_campaigns import repo
from tests.test_campaign_projects import ready
from tests.test_backtest_jobs import wait_for
from app.backtesting.strategies import strategy_registry
from app.research_agent.campaign_projects import provision
from app.research_agent.director import ResearchDirector, permitted
from app.research_agent.repository import ResearchRepository
from app.research_agent import workflow
from app.services.backtest_jobs import BacktestJobs
from app.storage.backtest_run_repository import BacktestRunRepository


class Backtest:
    """Synthetic calculation; use the real durable queue, scope and save path."""
    def __init__(self, database):
        self.database = database
        self.calls = []
        self.fail_first = False
        self.block = Event()
        self.block.set()

    def run(self, payload, progress, persist):
        workflow.validate_submission(self.database, payload)
        self.calls.append(payload)
        if self.fail_first and len(self.calls) == 1:
            raise ValueError('Synthetic provider failure')
        self.block.wait(10)
        progress('running', 1, 1)
        return persist(lambda: BacktestRunRepository(self.database).create(config=payload, result=dict(
            trades=[], metrics={}, equity_curve=[], data={'fingerprint': 'fixture'}, strategy=dict(key=payload['strategy_key'],
                implementation=strategy_registry.provenance(payload['strategy_key'])))))


@pytest.fixture
def execution(repo):
    campaign = ready(repo)
    links = provision(repo.database, campaign['id'])
    backtest = Backtest(repo.database)
    jobs = BacktestJobs(repo.database, backtest, workers=1)
    services = SimpleNamespace(database=repo.database, backtest_jobs=jobs)
    director = ResearchDirector(services, start_thread=False)
    configurations = {x['project_id']: dict(starting_balance=10000, risk_value=1,
        commission_per_order=1, spread_bps=1, slippage_bps=1, max_leverage=1) for x in links}
    yield director, campaign, configurations, backtest
    backtest.block.set()
    director.close()
    jobs.close()


def advance_until(director, identifier, state):
    def done():
        director.tick()
        return director.campaigns.get(identifier)['status'] == state
    wait_for(done)


def test_campaign_runs_projects_without_browser_and_reserves_once(execution):
    director, campaign, configs, backtest = execution
    started = director.start_baselines(campaign['id'], configs)
    assert started['reserved']['simulations'] == 2
    assert director.start_baselines(campaign['id'], configs) == started
    advance_until(director, campaign['id'], 'BASELINES_COMPLETE')
    assert len(backtest.calls) == 2
    assert all(e['state'] == 'COMPLETED' for e in director.campaigns.get(campaign['id'])['execution']['entries'])
    assert len(director.services.backtest_jobs.list()) == 2
    assert all(d['state'] == 'LOCKED_HOLDOUT' for p in started['projects']
               for d in ResearchRepository(director.database).get(p['project_id'])['datasets'] if d['state'] != 'DEVELOPMENT')


def test_one_project_failure_does_not_kill_campaign(execution):
    director, campaign, configs, backtest = execution
    backtest.fail_first = True
    director.start_baselines(campaign['id'], configs)
    advance_until(director, campaign['id'], 'BASELINES_COMPLETE')
    entries = director.campaigns.get(campaign['id'])['execution']['entries']
    assert [e['state'] for e in entries] == ['FAILED', 'COMPLETED']


def test_restart_after_enqueue_does_not_duplicate_job_or_evidence(execution):
    director, campaign, configs, backtest = execution
    director.start_baselines(campaign['id'], configs)
    director.tick()
    wait_for(lambda: director.services.backtest_jobs.list()[0]['status'] == 'completed')
    restarted = ResearchDirector(director.services, start_thread=False)
    advance_until(restarted, campaign['id'], 'BASELINES_COMPLETE')
    assert len(backtest.calls) == 2
    assert len(director.services.backtest_jobs.list()) == 2
    restarted.tick()
    assert len(backtest.calls) == 2


def test_background_service_progresses_without_tick_from_browser(execution):
    director, campaign, configs, backtest = execution
    director.start_baselines(campaign['id'], configs)
    background = ResearchDirector(director.services)
    try:
        # Wake the backend event directly to avoid slow sleeps in the test. No API
        # request executes advance or performs a state transition on its behalf.
        def done():
            background.wake.set()
            return background.campaigns.get(campaign['id'])['status'] == 'BASELINES_COMPLETE'
        wait_for(done)
        assert len(backtest.calls) == 2
    finally:
        background.close()


def test_pause_cancels_current_and_resume_does_not_reset_deadline_or_retry(execution):
    director, campaign, configs, backtest = execution
    backtest.block.clear()
    start = director.start_baselines(campaign['id'], configs)
    director.tick()
    wait_for(lambda: bool(backtest.calls))
    project = start['execution']['entries'][0]['project_id']
    director.control(campaign['id'], 'pause')
    assert not permitted(director.database, project)
    backtest.block.set()
    wait_for(lambda: director.services.backtest_jobs.list()[0]['status'] == 'cancelled')
    resumed = director.control(campaign['id'], 'resume')
    assert resumed['deadline'] == start['deadline']
    advance_until(director, campaign['id'], 'BASELINES_COMPLETE')
    assert len(backtest.calls) == 2  # cancelled first baseline was not run again


def test_stop_after_current_and_cancel_do_not_start_next_project(execution):
    director, campaign, configs, backtest = execution
    backtest.block.clear()
    director.start_baselines(campaign['id'], configs)
    director.tick()
    wait_for(lambda: bool(backtest.calls))
    director.control(campaign['id'], 'stop_after_current')
    backtest.block.set()
    advance_until(director, campaign['id'], 'PAUSED')
    assert len(backtest.calls) == 1
    assert director.control(campaign['id'], 'cancel')['status'] == 'CANCELLED'
    director.tick()
    assert len(backtest.calls) == 1


def test_wall_budget_exhaustion_prevents_dispatch(execution):
    director, campaign, configs, backtest = execution
    started = director.start_baselines(campaign['id'], configs)
    from datetime import datetime
    director.clock = lambda: datetime.fromisoformat(started['deadline']) + timedelta(seconds=1)
    director.tick()
    assert director.campaigns.get(campaign['id'])['status'] == 'BUDGET_EXHAUSTED'
    assert not backtest.calls


def test_costs_scope_and_configuration_are_not_silently_invented(execution):
    director, campaign, configs, backtest = execution
    pid = next(iter(configs))
    configs[pid].pop('spread_bps')
    with pytest.raises(ValueError, match='Explicit finite'): director.start_baselines(campaign['id'], configs)
    configs[pid]['spread_bps'] = 1
    configs[pid]['start_date'] = '2000-01-01'
    with pytest.raises(ValueError, match='boundaries'): director.start_baselines(campaign['id'], configs)
    assert not backtest.calls


def test_manual_route_cannot_bypass_campaign_reservations(execution):
    director, campaign, configs, backtest = execution
    started = director.start_baselines(campaign['id'], configs)
    entry = started['execution']['entries'][0]
    with pytest.raises(ValueError, match='Director'):
        workflow.start(director.services, entry['project_id'], entry['payload'])
    assert not backtest.calls


@pytest.fixture
def numeric_execution(repo):
    from app.research_agent.campaign_policy import CampaignPolicy
    from app.research_agent.loop import ResearchLoop
    from tests.test_research_campaigns import coverage
    from tests.test_research_committee import FakeModel
    policy = CampaignPolicy(send_development_summaries=True)
    campaign = repo.create(dict(request_key='numeric', mode='FIND_STRATEGIES', policy=policy.model_dump()))
    # Pick a real registry contract with a tunable numeric parameter. Model output
    # uses an existing declared value; no strategy source is generated in this test.
    spec = next(s for s in strategy_registry.specs() if any(p.kind in {'int','float'} for p in (*s.parameters,*s.research_parameters)))
    param = next(p for p in (*spec.parameters,*spec.research_parameters) if p.kind in {'int','float'})
    campaign = repo.prepare(campaign['id'], [dict(family_id=f, strategy_key=spec.key, reason='Fixture queue') for f in ['one','two']], [coverage()])
    links = provision(repo.database, campaign['id'])
    model = FakeModel(dict(description='Control-value hypothesis', rationale='Synthetic test', feature=param.key,
                          expected_result='Identical control', falsification='Different result',
                          axes=[dict(parameter=param.key, mode='explicit', values=[param.default])]))
    model.status = lambda: dict(configured=True, model='fixture', provider='fixture', pricing=dict(
        model='fixture', input_usd_per_million=1, output_usd_per_million=1,
        input_token_reservation=100000, output_token_reservation=4096, call_reservation_microusd=104096))
    backtest = Backtest(repo.database)
    jobs = BacktestJobs(repo.database, backtest, workers=1)
    loop = ResearchLoop(repo.database, jobs, model, start_thread=False)
    services = SimpleNamespace(database=repo.database, backtest_jobs=jobs, research_loop=loop)
    director = ResearchDirector(services, start_thread=False)
    configs = {p['project_id']: dict(starting_balance=10000, risk_value=1, commission_per_order=1,
                                    spread_bps=1, slippage_bps=1, max_leverage=1) for p in links}
    yield director, campaign, configs, backtest, model
    loop.close(); director.close(); jobs.close()


def test_director_runs_committee_hypotheses_and_control_variants_across_families(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    start = director.start_baselines(campaign['id'], configs, numeric_cycles=1)
    def done():
        director.tick()
        director.services.research_loop.tick()
        return director.campaigns.get(campaign['id'])['status'] == 'DEVELOPMENT_COMPLETE'
    wait_for(done)
    final = director.campaigns.get(campaign['id'])
    assert [e['state'] for e in final['execution']['entries']] == ['COMPLETED','COMPLETED'], final
    assert len(model.calls) == 6
    assert len(backtest.calls) == 6  # baseline + control + one variant per family
    assert final['reserved'] == start['reserved']
    from app.research_agent.trials import Trials
    trials = Trials(director.database).list()
    assert len(trials) == 2 and all(t['control_parity'] for t in trials)
    assert all(t['status'] == 'COMPLETED' for t in trials)
    director.tick(); director.services.research_loop.tick()
    assert len(model.calls) == 6 and len(backtest.calls) == 6


def test_numeric_budget_and_model_consent_checked_before_any_calls(execution):
    director, campaign, configs, backtest = execution
    with pytest.raises(ValueError, match='authorize sending'):
        director.start_baselines(campaign['id'], configs, numeric_cycles=1)
    assert not backtest.calls


def test_parameter_mining_limit_rejects_excess_cycles(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    with pytest.raises(ValueError, match='parameter-research'):
        director.start_baselines(campaign['id'], configs, numeric_cycles=3)
    assert not model.calls and not backtest.calls


def test_model_failure_moves_to_next_family_without_unbounded_retry(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    def failed(*args):
        model.calls.append(args)
        raise RuntimeError('Sensitive fixture message must not be persisted')
    model.generate = failed
    director.start_baselines(campaign['id'], configs, numeric_cycles=1)
    def done():
        director.tick(); director.services.research_loop.tick()
        return director.campaigns.get(campaign['id'])['status'] == 'DEVELOPMENT_COMPLETE'
    wait_for(done)
    result = director.campaigns.get(campaign['id'])
    assert all(e['state'] == 'RESEARCH_STOPPED' for e in result['execution']['entries'])
    assert len(model.calls) == 2 and len(backtest.calls) == 2
    assert 'Sensitive fixture' not in json.dumps(result)


def test_changed_model_pricing_blocks_campaign_model_execution(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    director.start_baselines(campaign['id'], configs, numeric_cycles=1)
    original = model.status()
    model.status = lambda: {**original, 'model':'changed'}
    advance_until(director, campaign['id'], 'DEVELOPMENT_COMPLETE')
    assert not model.calls
    assert all(e['state'] == 'FAILED' for e in director.campaigns.get(campaign['id'])['execution']['entries'])


def test_pause_revokes_campaign_model_and_trial_authority(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    director.start_baselines(campaign['id'], configs, numeric_cycles=1)
    def numeric():
        director.tick()
        return director.campaigns.get(campaign['id'])['execution']['entries'][0]['state'] == 'NUMERIC'
    wait_for(numeric)
    director.tick()  # Creates durable loop authorization, but no model call yet.
    director.control(campaign['id'], 'pause')
    director.services.research_loop.tick()
    assert not model.calls
    from app.research_agent.loop import require_active
    pid = director.campaigns.get(campaign['id'])['execution']['entries'][0]['project_id']
    loop = director.services.research_loop.get(pid)
    with director.database.connect() as c:
        with pytest.raises(ValueError): require_active(c, pid, loop['id'])


def test_campaign_api_defaults_scope_and_explicit_development_authority(execution):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_campaigns import router
    director, campaign, configs, backtest = execution
    director.services.research_director = director
    app = FastAPI(); app.state.services = director.services; app.include_router(router)
    base = '/strategy-lab/research-campaigns'
    with TestClient(app) as client:
        assert client.get(base+'/policy').json()['presets']['STANDARD']['budget']['wall_minutes'] == 1440
        assert client.post(base+'/'+campaign['id']+'/development', json={'configurations':configs}).status_code == 422
        response = client.post(base+'/'+campaign['id']+'/development', json=dict(configurations=configs,
            acknowledgement='Authorize frozen campaign development runs and configured model summaries'))
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'ACTIVE'
        assert client.get(base+'/'+campaign['id']).json()['summary']['execution_available']
        assert client.post(base+'/'+campaign['id']+'/deploy').status_code == 422
        assert client.post(base+'/'+campaign['id']+'/pause').json()['status'] == 'PAUSED'


def test_stop_after_current_does_not_start_another_numeric_cycle(numeric_execution):
    director, campaign, configs, backtest, model = numeric_execution
    director.start_baselines(campaign['id'], configs, numeric_cycles=2)
    def trial_started():
        director.tick(); director.services.research_loop.tick()
        pid = director.campaigns.get(campaign['id'])['execution']['entries'][0]['project_id']
        loop = director.services.research_loop.get(pid)
        return loop and loop['phase'] == 'WAIT'
    wait_for(trial_started)
    director.control(campaign['id'], 'stop_after_current')
    def stopped():
        director.tick(); director.services.research_loop.tick()
        return director.campaigns.get(campaign['id'])['status'] == 'PAUSED'
    wait_for(stopped)
    assert len(model.calls) == 3
    assert len(backtest.calls) == 3  # one baseline, one control, one variant
