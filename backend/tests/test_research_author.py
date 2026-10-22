from copy import deepcopy
import json
import os
from types import SimpleNamespace

import pytest

from tests.test_research_trials import research
from app.research_agent.author import CodeAuthor, CONSENT, archived_parent
from app.research_agent.committee import Committee
from app.research_agent.quarantine import export_draft
from app.research_agent.spending import quote


class Model:
    def __init__(self):
        self.calls = []
        self.reject = False
        self.abstain = False
        self.mutate = None
        self.source = None

    def status(self):
        return dict(configured=True, provider='fixture', model='fixture', pricing=quote(SimpleNamespace(
            research_llm_model='fixture', research_llm_input_usd_per_million=1,
            research_llm_output_usd_per_million=2, research_llm_max_output_tokens=1000)))

    def generate(self, role, instructions, evidence, schema):
        self.calls.append((role, deepcopy(evidence)))
        if role == 'Researcher':
            result = dict(decision='ABSTAIN' if self.abstain else 'PROPOSE', description='Single structural change',
                rationale='Test fixture', feature='Skip entries', expected_result='Fewer trades', falsification='Same entries')
        elif role == 'Devil':
            result = dict(verdict='CHALLENGE', concerns=['Low sample'], alternative_explanations=['Noise'], required_checks=['Winner retention'])
        elif role == 'Manager':
            result = dict(decision='REJECT' if self.reject else 'AUTHOR_CHILD', explanation='Test only, not promotion')
        else:
            from tests.test_sandbox_research_loop import SOURCE
            result = dict(source=self.source or SOURCE.replace('research_child_loop', evidence['child_registry_key']).replace("{'enabled':False}", "{'skip':0,'enabled':False}").replace('enabled', 'research_feature_enabled'), implementation_notes='One change')
        result['evidence_refs'] = ['summary']
        usage = dict(input_tokens=100, output_tokens=100)
        if self.mutate:
            self.mutate(role, result, usage)
        return result, usage


@pytest.fixture
def author(research, monkeypatch):
    db, _, project, _, _, _ = research
    with db.connect() as c:
        document = json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?', (project['id'],)).fetchone()[0])
        document['research_budget']['max_llm_spend_usd'] = 10
        c.execute('UPDATE agent_projects SET document=? WHERE id=?', (json.dumps(document), project['id']))
    # The synthetic strategy is defined in a test function and has no historic
    # module archive. Production archive handling is tested separately below.
    monkeypatch.setattr('app.research_agent.author.archived_parent', lambda *args: dict(source='SYNTHETIC_PARENT', sha256='fixture'))
    model = Model()
    service = CodeAuthor(db, model)
    yield service, model, project['id']
    service.close()


def finish(service, pid, key='one'):
    item = service.start(pid, dict(request_key=key, consent=CONSENT))
    if service.thread:
        service.thread.join(timeout=15)
        assert not service.thread.is_alive()
    return next(r for r in service.list(pid) if r['id'] == item['id'])


def test_author_roles_shared_reservations_lineage_and_no_host_execution(author, tmp_path, research):
    service, model, pid = author
    sentinel = tmp_path / 'must-not-exist'
    model.source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('unsafe')\n"
    jobs = research[4]
    before = len(jobs.list())
    result = finish(service, pid)
    assert result['status'] == 'COMPLETED', result
    assert [r for r, _ in model.calls] == ['Researcher', 'Devil', 'Manager', 'CodeAuthor']
    assert 'Devil' in model.calls[2][1]['prior_roles']
    assert result['reserved_calls'] == 4 and result['reserved_cost_microusd'] == 1008000
    assert result['execution_enabled'] is False
    assert result['operation']['role']=='CodeAuthor' and result['operation']['status']=='RETURNED'
    assert result['updated_at'] and result['finished_at']
    draft = export_draft(service.database, pid, result['candidate_id'], result['draft_id'])
    assert draft['source'] == model.source.strip() and not sentinel.exists()
    assert draft['draft']['parent_hash'] == result['parent_hash']
    assert len(jobs.list()) == before
    assert finish(service, pid) == result and len(model.calls) == 4
    assert 'LOCKED_HOLDOUT' not in json.dumps(model.calls) and '2027-' not in json.dumps(model.calls)
    assert Committee(service.database, model).public(pid)['reserved_calls'] == 4


@pytest.mark.parametrize('mode', ['reject', 'abstain'])
def test_challenge_can_stop_before_code_author(author, mode):
    service, model, pid = author
    setattr(model, mode, True)
    result = finish(service, pid)
    assert result['status'] == 'REJECTED' and len(model.calls) == 3
    assert 'draft_id' not in result


def test_author_and_numeric_committee_share_call_budget(author):
    service, model, pid = author
    with service.database.connect() as c:
        doc = json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?', (pid,)).fetchone()[0])
        doc['research_budget']['max_llm_calls'] = 4
        c.execute('UPDATE agent_projects SET document=? WHERE id=?', (json.dumps(doc), pid))
    assert finish(service, pid)['status'] == 'COMPLETED'
    with pytest.raises(ValueError, match='call budget'):
        Committee(service.database, model).review(pid, 'numeric')
    with pytest.raises(ValueError, match='call budget'):
        finish(service, pid, 'second')
    assert len(model.calls) == 4


def test_larger_parent_is_sent_exactly_and_reserves_updated_cost(author, monkeypatch):
    service, model, pid = author
    source = '#'+('x'*70000)
    monkeypatch.setattr('app.research_agent.author.archived_parent',
                        lambda *args: dict(source=source, sha256='fixture'))
    result = finish(service, pid, 'large-parent')
    assert result['status']=='COMPLETED',result.get('error')
    assert len(model.calls)==4
    assert all(evidence['archived_parent']['source']==source for _,evidence in model.calls)
    assert result['reserved_cost_microusd']==4*model.status()['pricing']['call_reservation_microusd']


@pytest.mark.parametrize('fault', ['unknown_ref', 'excess_usage', 'pause'])
def test_author_fails_closed_without_retries(author, research, fault):
    service, model, pid = author
    def mutate(role, result, usage):
        if fault == 'unknown_ref':
            result['evidence_refs'] = ['invented']
        elif fault == 'excess_usage':
            usage['input_tokens'] = model.status()['pricing']['input_token_reservation'] + 1
        else:
            research[1].transition(pid, 'PAUSED')
    model.mutate = mutate
    result = finish(service, pid)
    assert result['status'] == 'FAILED' and len(model.calls) == 1
    assert 'draft_id' not in result
    assert finish(service, pid)['id'] == result['id'] and len(model.calls) == 1
    if fault == 'excess_usage':
        with pytest.raises(ValueError, match='spending is blocked'):
            Committee(service.database, model).review(pid, 'numeric')


def test_restart_never_repeats_unknown_paid_author_call(author):
    service, model, pid = author
    result = finish(service, pid)
    result['status'] = 'RUNNING'
    with service.database.connect() as c:
        c.execute('UPDATE agent_reviews SET document=? WHERE id=?', (json.dumps(result), result['id']))
    restarted = CodeAuthor(service.database, model)
    try:
        assert finish(restarted, pid)['status'] == 'INTERRUPTED'
        assert len(model.calls) == 4
        assert restarted.committee.public(pid)['reserved_calls'] == 4
    finally:
        restarted.close()


def test_missing_archive_never_substitutes_current_source(research):
    db, _, project, _, _, _ = research
    with pytest.raises(ValueError, match='No captured source archive'):
        archived_parent(db, project['baseline_run_id'], project['strategy_provenance'])


def test_author_api_consent_status_and_idempotence(author):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.research_agent import router
    service, model, pid = author
    app = FastAPI()
    app.include_router(router)
    app.state.services = SimpleNamespace(database=service.database, research_author=service)
    url = '/strategy-lab/research-agent/' + pid + '/code-author'
    with TestClient(app) as client:
        assert client.post(url, json={'request_key': 'api'}).status_code == 422
        assert not model.calls
        response = client.post(url, json=dict(request_key='api', consent=CONSENT))
        assert response.status_code == 200, response.text
        service.thread.join(timeout=15)
        result = client.get(url).json()['items'][0]
        assert result['status'] == 'COMPLETED'
        assert client.post(url, json=dict(request_key='api', consent=CONSENT)).json()['id'] == result['id']
        assert len(model.calls) == 4


@pytest.mark.skipif(os.environ.get('LEDGER_TEST_DOCKER') != '1', reason='Opt-in author to Docker acceptance')
def test_mocked_author_to_real_docker_control_causality_and_immutable_parent(author, research):
    from tests.test_sandbox_research_loop import setup, finish as finish_docker
    from app.research_agent.candidates import Candidates
    from app.research_agent.sandbox_runs import ACK
    service, model, pid = author
    result = finish(service, pid)
    assert result['status'] == 'COMPLETED', result
    reference = next(c for c in Candidates(service.database).list(pid) if c['id'] == result['candidate_id'])
    # Reuse the fixture's queue-only validator adaptation, not a mock sandbox.
    runner, _, _, _, _ = setup((research, reference))
    before = research[5].runs.get(reference['run_id'])
    try:
        output = finish_docker(runner, runner.approve(pid, reference['id'], result['draft_id'], dict(
            control_parameters={'skip': 0, 'research_feature_enabled': False},
            candidate_parameters={'skip': 0, 'research_feature_enabled': True},
            timeout_seconds=60, acknowledgement=ACK)))
        assert output['status'] == 'COMPLETED', json.dumps(output, indent=2)
        assert output['control_parity'] and output['causality']['prefix_match']
        assert research[5].runs.get(reference['run_id']) == before
    finally:
        runner.close()
