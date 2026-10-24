"""Bounded validation diagnostics; never retain rejected model text or evidence values."""
from datetime import datetime, timezone
from hashlib import sha256
from .llm import ModelFailure


def validate_evidence(document, references, evidence):
    invalid = [ref for ref in references if ref not in evidence]
    if not invalid:
        return
    # A reference is untrusted model output and could itself contain a secret.
    # Hash it rather than copying it to a log, database diagnostic or browser.
    document['validation_diagnostic'] = dict(
        version=1, timestamp=datetime.now(timezone.utc).isoformat(),
        component='research.model.validation', operation='evidence_reference_validation',
        level='ERROR', status='rejected', error_code='UNKNOWN_EVIDENCE_REFERENCE',
        message='The model cited an ID outside the supplied evidence map.',
        suggested_action='Use exact evidence IDs supplied in this request. Do not retry automatically.',
        retryable=False, role=document.get('operation', {}).get('role'),
        details=dict(invalid_reference_count=len(invalid), supplied_evidence_count=len(evidence),
                     rejected_reference_sha256=[sha256(ref.encode()).hexdigest() for ref in invalid[:12]]))
    raise ModelFailure('unknown_evidence_reference')


def public_validation(record):
    """Reconstruct a safe presentation, including legacy failures without details."""
    if record.get('error') != 'unknown_evidence_reference':
        return None
    stored = record.get('validation_diagnostic') or {}
    details = stored.get('details') or {}
    safe = {key: details[key] for key in ('invalid_reference_count', 'supplied_evidence_count')
            if type(details.get(key)) is int and 0 <= details[key] <= 100000}
    return dict(event_id=record['id'] + ':evidence_reference_validation',
                timestamp=record.get('finished_at'), component='research.model.validation',
                operation='evidence_reference_validation', level='ERROR',
                error_code='UNKNOWN_EVIDENCE_REFERENCE', retryable=False,
                message='The model cited an ID outside the supplied evidence map.',
                suggested_action='Use exact supplied evidence IDs; no automatic retry.',
                details=safe, legacy_details_unavailable=not bool(stored))
