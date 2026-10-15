import json

import pytest

from tests.test_research_author import author, finish
from tests.test_research_trials import research
from app.research_agent.research_ledger import development_history


def history(service, pid):
    with service.database.connect() as c:
        return development_history(c, [pid, pid, None])


def test_proposal_is_durably_frozen_before_code_and_next_author_sees_it(author):
    service, model, pid = author
    def inspect(role, output, usage):
        if role == 'CodeAuthor':
            stored = service.list(pid)[-1]
            assert stored['hypothesis']['proposal'] == stored['roles']['Researcher']
            assert 'CodeAuthor' not in stored['roles'] and 'draft_id' not in stored
            assert history(service, pid)['records'][-1]['preregistration'] == 'VERIFIED'
    model.mutate = inspect
    first = finish(service, pid)
    assert first['status'] == 'COMPLETED', first
    model.mutate = None
    second = finish(service, pid, 'second')
    assert second['error'] == 'duplicate_structural_source_no_retest'
    prior = model.calls[4][1]['development_search_history']
    assert prior['debt']['structural_author_requests'] == 1
    assert any(r['id'] == first['id'] for r in prior['records'])
    ledger = history(service, pid)
    assert ledger['debt']['structural_author_requests'] == 2
    assert ledger['debt']['failed_or_interrupted'] == 1
    assert ledger['debt']['structural_drafts'] == 1
    assert len([r for r in ledger['records'] if r['kind'] == 'STRUCTURAL']) == 2
    assert history(service, pid) == ledger  # Restart/read does not erase or duplicate debt.


@pytest.mark.parametrize('mode', ['reject', 'abstain'])
def test_rejected_proposals_stay_visible_without_counting_as_executed(author, mode):
    service, model, pid = author
    setattr(model, mode, True)
    result = finish(service, pid)
    ledger = history(service, pid)
    assert result['status'] == 'REJECTED'
    assert ledger['debt']['rejected_before_execution'] == 1
    assert ledger['debt']['structural_drafts'] == 0
    record = next(r for r in ledger['records'] if r['id'] == result['id'])
    assert record['challenge']['concerns'] == ['Low sample']
    assert record['proposal']['falsification'] == 'Same entries'


def test_history_excludes_unrelated_projects_source_and_validation_results(author):
    service, _, pid = author
    finish(service, pid)
    with service.database.connect() as c:
        # A protected-result table must never be queried, even if it is available.
        c.execute('CREATE TABLE IF NOT EXISTS ledger_secret_fixture(secret TEXT)')
        c.execute('INSERT INTO ledger_secret_fixture VALUES (?)', ('HOLDOUT_SENTINEL',))
        statements = []
        c.set_trace_callback(statements.append)
        ledger = development_history(c, [pid])
        assert not any('ledger_secret_fixture' in q or 'agent_validations' in q or 'backtest_runs' in q for q in statements)
        assert development_history(c, ['unrelated'])['records'] == []
    encoded = json.dumps(ledger)
    assert 'HOLDOUT_SENTINEL' not in encoded and 'SYNTHETIC_PARENT' not in encoded
    assert 'implementation_notes' not in encoded


def test_legacy_records_are_labelled_and_tampering_blocks_new_spending(author):
    service, model, pid = author
    item = finish(service, pid)
    original = item.pop('hypothesis')
    def replace():
        with service.database.connect() as c:
            c.execute('UPDATE agent_reviews SET document=? WHERE id=?', (json.dumps(item), item['id']))
    replace()
    assert next(r for r in history(service, pid)['records'] if r['id'] == item['id'])['preregistration'] == 'LEGACY_RECONSTRUCTED'
    item['hypothesis'] = original
    item['hypothesis']['proposal']['feature'] = 'changed after test'
    replace()
    assert history(service, pid)['debt']['integrity_errors'] == 1
    with pytest.raises(ValueError, match='integrity'):
        finish(service, pid, 'next')
    assert len(model.calls) == 4


def test_numeric_and_structural_history_share_counts_without_double_counting(author):
    service, _, pid = author
    finish(service, pid)
    before = history(service, pid)
    with service.database.connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS agent_hypotheses(id TEXT PRIMARY KEY, project_id TEXT, request_key TEXT, document TEXT)')
        h = dict(id='numeric', status='PREREGISTERED', description='One parameter',
                 plan={'job_count': 3}, base_config={'secret': 'not included'})
        c.execute('INSERT INTO agent_hypotheses VALUES (?,?,?,?)', ('numeric', pid, 'numeric', json.dumps(h)))
    ledger = history(service, pid)
    assert ledger['debt']['numeric_hypotheses'] == before['debt']['numeric_hypotheses'] + 1
    assert ledger['debt']['numeric_variants_planned'] == before['debt']['numeric_variants_planned'] + 3
    assert len(ledger['records']) == len(before['records']) + 1
    assert 'not included' not in json.dumps(ledger)


def test_restart_preserves_interrupted_hypothesis_without_another_model_call(author):
    from app.research_agent.author import CodeAuthor
    service, model, pid = author
    item = finish(service, pid)
    item['status'] = 'RUNNING'
    with service.database.connect() as c:
        c.execute('UPDATE agent_reviews SET document=? WHERE id=?', (json.dumps(item), item['id']))
    restarted = CodeAuthor(service.database, model)
    try:
        assert finish(restarted, pid)['status'] == 'INTERRUPTED'
        ledger = history(restarted, pid)
        record = next(r for r in ledger['records'] if r['id'] == item['id'])
        assert record['preregistration'] == 'VERIFIED'
        assert ledger['debt']['failed_or_interrupted'] == 1
        assert len(model.calls) == 4
    finally:
        restarted.close()


def test_old_manual_validation_hypothesis_is_redacted_from_author_context(author):
    service, _, pid = author
    with service.database.connect() as c:
        h = dict(id='validation-derived', status='PREREGISTERED', description='PRIVATE_VALIDATION_FINDING',
                 rationale='PRIVATE_VALIDATION_FINDING', discovery_dataset_ids=['unverified-protected'],
                 devils_advocate_objections='PRIVATE_VALIDATION_FINDING', plan={'job_count': 2})
        c.execute('INSERT INTO agent_hypotheses VALUES (?,?,?,?)', (h['id'], pid, h['id'], json.dumps(h)))
    ledger = history(service, pid)
    assert ledger['debt']['redacted_scope_records'] == 1
    assert 'PRIVATE_VALIDATION_FINDING' not in json.dumps(ledger)
    record = next(r for r in ledger['records'] if r['id'] == h['id'])
    assert record['proposal'] is None and record['evidence_scope'] == 'REDACTED_UNVERIFIED_SCOPE'
