"""Durable development closeout, separate from validated candidate decisions."""
from .analysis import digest


def entry_hash(entry):
    return digest({key: value for key, value in entry.items() if key != 'disposition'})


def close(entry, policy):
    state = entry['state']
    if state not in {'COMPLETED', 'RESEARCH_STOPPED', 'FAILED'}:
        raise ValueError('Cannot close an active research family')
    decision = entry.get('research_decision') or {}
    verdict = decision.get('verdict')
    reasons = list(decision.get('reasons', []))
    if state == 'FAILED' or verdict == 'INVALID_EXECUTION':
        outcome = 'EXECUTION_BLOCKED'
        reasons.append(entry.get('error') or 'Execution did not produce valid development evidence.')
    elif entry.get('frozen_candidate_id') and entry.get('frozen_candidate_hash'):
        outcome = 'FROZEN_REQUIRES_VALIDATION'
        reasons.append('A generated candidate was frozen; development does not grant acceptance.')
    elif verdict == 'REJECTED_DEVELOPMENT':
        outcome = 'ABANDONED_DEVELOPMENT'
        reasons.append('No more structural attempts are scheduled under this campaign allocation.')
    elif verdict == 'INSUFFICIENT_EVIDENCE':
        outcome = 'INCONCLUSIVE'
        reasons.append('Insufficient evidence is not a finding that the strategy cannot work.')
    elif state == 'RESEARCH_STOPPED':
        outcome = 'STOPPED_WITHOUT_CONCLUSION'
        reasons.append(entry.get('reason') or 'Research stopped before a complete development conclusion.')
    elif entry.get('structural') or entry.get('numeric_cycles'):
        outcome = 'REVIEW_REQUIRED'
        reasons.append('No verified generated candidate disposition is available; inspect the saved research records.')
    else:
        outcome = 'BASELINE_ONLY'
        reasons.append('Baseline execution completed without a research promotion decision.')
    return dict(version='family_development_closeout_v1', outcome=outcome,
                reasons=list(dict.fromkeys(reasons)), entry_sha256=entry_hash(entry),
                policy_sha256=digest(policy), candidate_id=entry.get('frozen_candidate_id'),
                candidate_hash=entry.get('frozen_candidate_hash'),
                structural_attempts=len(entry.get('structural_attempts', [])),
                automatic_acceptance=False, deployment_authorized=False)


def verified(entry, policy):
    record = entry.get('disposition')
    if record is None:
        return None  # Never manufacture a historical closeout.
    if record != close(entry, policy):
        raise ValueError('Family development closeout no longer matches its evidence')
    return record
