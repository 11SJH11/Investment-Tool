"""Development-only search history projected from durable research records.

No result loading, validation reads, model arithmetic or new execution authority.
Counts describe repeated research exposure, not a statistical correction.
"""
import json

from .analysis import digest


def preregistration(review):
    """Freeze the validated proposal before any generated implementation exists."""
    proposal = review['roles']['Researcher']
    record = dict(version='structural_hypothesis_v1', author_id=review['id'],
                  parent_hash=review['parent_hash'], evidence_hash=review['evidence_hash'],
                  discovery_dataset_ids=list(review['discovery_dataset_ids']),
                  proposal=dict(proposal))
    return {**record, 'sha256': digest(record)}


def development_history(connection, project_ids):
    """Read only explicitly linked projects, including incomplete/failed attempts.

    Legacy author records are labelled as reconstructed; never manufacture a
    historical preregistration timestamp or read validation performance.
    """
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    ids = sorted(set(identifier for identifier in project_ids if identifier))

    def documents(table):
        if table not in tables:
            return []
        return [json.loads(row[0]) for pid in ids for row in connection.execute(
            f'SELECT document FROM {table} WHERE project_id=? ORDER BY rowid', (pid,))]

    numeric = documents('agent_hypotheses')
    reviews = [r for r in documents('agent_reviews') if r.get('kind') == 'CODE_AUTHOR']
    development_ids = set()
    if 'agent_datasets' in tables:
        for row in connection.execute('SELECT document FROM agent_datasets'):
            dataset = json.loads(row[0])
            if dataset['state'] in {'DEVELOPMENT', 'INSPECTED'}:
                development_ids.add(dataset['id'])

    def development_only(record):
        dataset_ids = record.get('discovery_dataset_ids', [])
        return bool(dataset_ids) and set(dataset_ids) <= development_ids

    records = []
    for review in reviews:
        scoped = development_only(review)
        roles = review.get('roles', {}) if scoped else {}
        registered = review.get('hypothesis')
        proposal = (registered or {}).get('proposal', roles.get('Researcher')) if scoped else None
        valid = bool(registered and registered.get('sha256') == digest(
            {k: v for k, v in registered.items() if k != 'sha256'})
            and registered.get('author_id') == review['id']
            and registered.get('parent_hash') == review.get('parent_hash')
            and registered.get('evidence_hash') == review.get('evidence_hash')
            and registered.get('discovery_dataset_ids') == review.get('discovery_dataset_ids')
            and proposal == roles.get('Researcher'))
        records.append(dict(id=review['id'], kind='STRUCTURAL', status=review['status'],
            created_at=review.get('created_at'), proposal=proposal,
            evidence_scope='DEVELOPMENT' if scoped else 'REDACTED_UNVERIFIED_SCOPE',
            preregistration='SCOPE_UNVERIFIED' if not scoped else 'VERIFIED' if valid else 'INTEGRITY_ERROR' if registered else 'LEGACY_RECONSTRUCTED',
            hypothesis_sha256=registered.get('sha256') if registered else None,
            parent_hash=review.get('parent_hash'), evidence_hash=review.get('evidence_hash'),
            discovery_dataset_ids=review.get('discovery_dataset_ids', []),
            challenge=roles.get('Devil'), manager=roles.get('Manager'),
            draft_id=review.get('draft_id'), source_sha256=review.get('source_sha256'),
            error=review.get('error') if scoped else None))
    for hypothesis in numeric:
        records.append(dict(id=hypothesis['id'], kind='NUMERIC', status=hypothesis['status'],
            created_at=hypothesis.get('created_at'), hypothesis_sha256=hypothesis.get('proposal_hash'),
            evidence_scope='DEVELOPMENT' if development_only(hypothesis) else 'REDACTED_UNVERIFIED_SCOPE',
            proposal={k: hypothesis.get(k) for k in (
                'description', 'rationale', 'feature', 'expected_result', 'falsification')} if development_only(hypothesis) else None,
            challenge=hypothesis.get('devils_advocate_objections') if development_only(hypothesis) else None,
            planned_variants=hypothesis.get('plan', {}).get('job_count', 0)))
    records.sort(key=lambda r: (r.get('created_at') or '', r['id']))
    return dict(version='development_search_ledger_v1', records=records,
        debt=dict(structural_author_requests=len(reviews),
                  structural_proposals=sum('Researcher' in r.get('roles', {}) for r in reviews),
                  structural_drafts=sum(bool(r.get('draft_id')) for r in reviews),
                  failed_or_interrupted=sum(r['status'] in {'FAILED', 'INTERRUPTED'} for r in reviews),
                  rejected_before_execution=sum(r['status'] == 'REJECTED' for r in reviews),
                  numeric_hypotheses=len(numeric),
                  numeric_variants_planned=sum(h.get('plan', {}).get('job_count', 0) for h in numeric),
                  redacted_scope_records=sum(r['evidence_scope'] != 'DEVELOPMENT' for r in records),
                  integrity_errors=sum(r.get('preregistration') == 'INTEGRITY_ERROR' for r in records)),
        limitation='Development search exposure only. Counts are not independent trials, a statistical correction, or evidence of an edge. Failed attempts remain in the history. Validation evidence is excluded.')
