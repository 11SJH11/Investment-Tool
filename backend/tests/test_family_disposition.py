from copy import deepcopy

import pytest

from app.research_agent.family_disposition import close, verified


@pytest.mark.parametrize('fields,outcome', [
    ({}, 'BASELINE_ONLY'),
    ({'numeric_cycles': 1}, 'REVIEW_REQUIRED'),
    ({'structural': True}, 'REVIEW_REQUIRED'),
    ({'research_decision': {'verdict': 'REJECTED_DEVELOPMENT'}}, 'ABANDONED_DEVELOPMENT'),
    ({'research_decision': {'verdict': 'INSUFFICIENT_EVIDENCE'}}, 'INCONCLUSIVE'),
    ({'research_decision': {'verdict': 'INVALID_EXECUTION'}}, 'EXECUTION_BLOCKED'),
    ({'state': 'FAILED', 'error': 'timeout'}, 'EXECUTION_BLOCKED'),
    ({'state': 'RESEARCH_STOPPED', 'reason': 'author_restart_no_automatic_retry'}, 'STOPPED_WITHOUT_CONCLUSION'),
    ({'frozen_candidate_id': 'candidate', 'frozen_candidate_hash': 'hash'}, 'FROZEN_REQUIRES_VALIDATION'),
])
def test_closeout_distinguishes_results_without_granting_acceptance(fields, outcome):
    entry = {'state': 'COMPLETED', **fields}
    before = deepcopy(entry)
    record = close(entry, {'minimum_trades': 30})
    assert record['outcome'] == outcome
    assert record['reasons'] and not record['automatic_acceptance'] and not record['deployment_authorized']
    assert entry == before
    entry['disposition'] = record
    assert verified(entry, {'minimum_trades': 30}) == record


@pytest.mark.parametrize('change', ['policy', 'evidence', 'outcome'])
def test_changed_closeout_evidence_or_policy_is_rejected(change):
    entry = {'state': 'COMPLETED', 'structural': True}
    policy = {'minimum_trades': 30}
    entry['disposition'] = close(entry, policy)
    if change == 'policy': policy['minimum_trades'] = 1
    elif change == 'evidence': entry['frozen_candidate_id'] = 'new'
    else: entry['disposition']['outcome'] = 'ACCEPTED'
    with pytest.raises(ValueError, match='no longer matches'):
        verified(entry, policy)


def test_legacy_report_is_not_retroactively_closed_and_active_work_cannot_close():
    assert verified({'state': 'COMPLETED'}, {}) is None
    with pytest.raises(ValueError, match='active'):
        close({'state': 'SANDBOX'}, {})
