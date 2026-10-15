from copy import deepcopy

import pytest

from app.research_agent.feature_ablation import assess, VERSION
from app.research_agent.research_verdict import assess as triage
from app.research_agent.structural_candidates import verify_evidence
from tests.test_structural_candidates import evidence


def fixture():
    trial, parent, policy, original = evidence()
    trial['request'].update(control_parameters={'length': 20, 'research_feature_enabled': False},
                            candidate_parameters={'length': 20, 'research_feature_enabled': True})
    return trial, parent, {**policy, 'structural_simplification': VERSION}, original


def test_unchanged_child_prefers_parent_and_cannot_freeze_or_consume_holdout():
    trial, parent, policy, original = fixture()
    before = deepcopy(trial)
    decision = triage(trial, policy)
    assert decision['verdict'] == 'REJECTED_DEVELOPMENT'
    assert decision['simplification']['verdict'] == 'PREFER_SIMPLER_PARENT'
    assert decision['simplification']['additional_simulations'] == 0
    assert len(decision['simplification']['rows']) == 3
    assert not decision['accepted'] and not decision['validation_authorized']
    with pytest.raises(ValueError, match='Only promising'):
        verify_evidence(trial, parent, policy, original)
    assert trial == before


def test_legacy_policy_keeps_original_triage_and_snapshot_contract():
    trial, _, policy, _ = fixture()
    policy.pop('structural_simplification')
    decision = triage(trial, policy)
    assert decision['verdict'] == 'PROMISING_DEVELOPMENT'
    assert 'simplification' not in decision


def test_verified_improvement_remains_eligible_for_development_freeze():
    from app.research_agent.analysis import compare, digest, summary
    trial, parent, policy, original = fixture()
    identity = {'market_data_fingerprint': 'fixture'}
    for cell in [trial, *trial['robustness']['cells']]:
        cell['result']['trades'][0].update(r_multiple=2, net_pnl=20)
        cell['summary'] = summary(cell['result']['trades'])
        cell['result_sha256'] = digest(cell['result'])
        cell['comparison'] = compare({'config': identity, 'result': original},
                                     {'config': identity, 'result': cell['result']})
    decision = verify_evidence(trial, parent, policy, original)
    assert decision['verdict'] == 'PROMISING_DEVELOPMENT'
    assert decision['simplification']['verdict'] == 'FEATURE_CONTRIBUTION_OBSERVED'
    assert not decision['accepted'] and not decision['validation_authorized']


def test_observed_feature_contribution_does_not_replace_other_gates():
    trial, _, policy, _ = fixture()
    trial['summary']['average_r'] = 1.1
    assert assess(trial)['verdict'] == 'FEATURE_CONTRIBUTION_OBSERVED'
    assert triage(trial, policy)['verdict'] == 'PROMISING_DEVELOPMENT'
    trial['robustness']['cells'][0]['summary']['n'] = 0
    assert triage(trial, policy)['verdict'] == 'INSUFFICIENT_EVIDENCE'
    trial['robustness']['cells'][0]['summary']['n'] = 1
    trial['robustness']['cells'][0]['comparison']['removed_large_winners']['n'] = 1
    assert triage(trial, policy)['verdict'] == 'REJECTED_DEVELOPMENT'


@pytest.mark.parametrize('fault', ['another_parameter', 'missing_switch', 'truthy_switch',
    'bounded_anchor', 'bounded_windows', 'missing_cost', 'wrong_window', 'control',
    'prefix', 'window_control', 'window_prefix', 'missing_expectancy', 'nonfinite'])
def test_incomplete_or_nonpaired_ablation_fails_closed(fault):
    trial, _, policy, _ = fixture()
    if fault == 'another_parameter': trial['request']['candidate_parameters']['length'] = 21
    elif fault == 'missing_switch': trial['request']['control_parameters'].pop('research_feature_enabled')
    elif fault == 'truthy_switch': trial['request']['candidate_parameters']['research_feature_enabled'] = 1
    elif fault == 'bounded_anchor': trial['request']['full_period'] = False
    elif fault == 'bounded_windows': trial['request']['full_robustness_windows'] = False
    elif fault == 'missing_cost': trial['robustness']['cells'].pop()
    elif fault == 'wrong_window': trial['robustness']['cells'][0]['start'] = '2026-01-01'
    elif fault == 'control': trial['control_parity'] = False
    elif fault == 'prefix': trial['causality']['prefix_match'] = False
    elif fault == 'window_control': trial['robustness']['cells'][0]['control_parity'] = False
    elif fault == 'window_prefix': trial['robustness']['cells'][0]['prefix_signals_checked'] = 0
    elif fault == 'missing_expectancy': trial['comparison']['parent']['summary'].pop('average_r')
    elif fault == 'nonfinite': trial['summary']['average_r'] = None
    assert assess(trial)['verdict'] == 'INCOMPLETE'
    assert triage(trial, policy)['verdict'] != 'PROMISING_DEVELOPMENT'
