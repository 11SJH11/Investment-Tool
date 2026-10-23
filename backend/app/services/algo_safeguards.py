"""Project durable diagnostic evidence without acquiring execution authority."""
import json


def safeguards(connection, tables, policies):
    if not policies:
        return {}
    ids = [p['id'] for p in policies]
    accounts = sorted({p['policy']['account_key'] for p in policies})
    guards, attempts, assessments, diagnostics = {}, {}, {}, {}
    account_slots = ','.join('?' for _ in accounts)
    if 'mt5_execution_account_guards' in tables:
        guards = {r[0]: dict(state=r[1], since=r[2]) for r in connection.execute(
            f'SELECT account_key,state,created_at FROM mt5_execution_account_guards WHERE account_key IN ({account_slots})', accounts)}
    if 'mt5_execution_attempts' in tables:
        attempts = {r[0]: r[1] for r in connection.execute(
            f'SELECT account_key,COUNT(*) FROM mt5_execution_attempts WHERE account_key IN ({account_slots}) GROUP BY account_key', accounts)}
    if 'mt5_execution_risk_assessments' in tables:
        slots = ','.join('?' for _ in ids)
        rows = connection.execute(f'''SELECT policy_id,document FROM mt5_execution_risk_assessments
            WHERE rowid IN (SELECT MAX(rowid) FROM mt5_execution_risk_assessments
            WHERE policy_id IN ({slots}) GROUP BY policy_id)''', ids)
        for policy_id, document in rows:
            saved = json.loads(document)
            decision = saved.get('decision') or {}
            # Raw account facts, native responses and authority/guard tokens are
            # deliberately excluded. A passing diagnostic is not a reservation.
            assessments[policy_id] = {key: decision.get(key) for key in (
                'allowed', 'reasons', 'evaluated_at_ms', 'risk_day_utc',
                'projected_gross_exposure', 'projected_loss_budget', 'basis')}
    if {'mt5_t01_diagnostics', 'mt5_t01_decisions'} <= tables:
        slots = ','.join('?' for _ in ids)
        rows = connection.execute(f'''SELECT json_extract(d.definition,'$.policy_id'),d.id,d.revision,
            json_extract(r.document,'$.decision_at'),json_extract(r.document,'$.result.kind')
            FROM mt5_t01_diagnostics d LEFT JOIN mt5_t01_decisions r
            ON r.deployment_id=d.id AND r.sequence=d.revision
            WHERE d.rowid IN (SELECT MAX(rowid) FROM mt5_t01_diagnostics
            WHERE json_extract(definition,'$.policy_id') IN ({slots})
            GROUP BY json_extract(definition,'$.policy_id'))''', ids)
        diagnostics = {r[0]: dict(id=r[1], completed_decisions=r[2], last_decision_at=r[3],
            last_signal=r[4], mode='DIAGNOSTIC_ONLY', execution_enabled=False) for r in rows}
    return {p['id']: dict(
        guard=guards.get(p['policy']['account_key']),
        recorded_account_attempts=attempts.get(p['policy']['account_key'], 0)
            if 'mt5_execution_attempts' in tables else None,
        latest_risk_assessment=assessments.get(p['id']),
        latest_diagnostic_stream=diagnostics.get(p['id']),
        execution_enabled=False,
        evidence_kind='persisted_diagnostics',
    ) for p in policies}
