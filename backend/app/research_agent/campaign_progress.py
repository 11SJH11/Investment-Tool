"""Read-only persisted baseline/reference queue evidence, never holdout results."""
from datetime import datetime, timezone


def baseline_progress(database, campaign, *, now=None):
    now = now or datetime.now(timezone.utc)
    entries = campaign.get('execution', {}).get('entries', [])
    keys = {('agent-baseline:' + e[field]): (e['family_id'], field == 'reference_project_id')
            for e in entries for field in ('project_id', 'reference_project_id') if e.get(field)}
    rows = []
    with database.connect() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='backtest_jobs' AND type='table'").fetchone():
            for key, (family, reference) in keys.items():
                for raw in c.execute('''SELECT id,status,processed,total,run_id,error,created_at,updated_at
                        FROM backtest_jobs WHERE request_key=? ORDER BY ordinal''', (key,)):
                    row = dict(raw)
                    row.update(family_id=family, role='reference' if reference else 'baseline')
                    try:
                        stamp = datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00'))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=timezone.utc)
                        age = max(0., (now-stamp).total_seconds())
                    except (ValueError, TypeError):
                        age = None
                    row['seconds_since_queue_update'] = age
                    row['suspected_stall'] = row['status'] == 'running' and age is not None and age > 600
                    processed, total = row['processed'], row['total']
                    row['bar_progress_percent'] = (100*processed/total if type(processed) is int
                        and type(total) is int and total > 0 and 0 <= processed <= total else None)
                    rows.append(row)
    failures = [dict(family_id=e['family_id'], reason=e.get('error') or e.get('reason') or e['state'])
                for e in entries if e['state'] in {'FAILED', 'RESEARCH_STOPPED'}]
    terminal = campaign['status'] in {'BASELINES_COMPLETE', 'DEVELOPMENT_COMPLETE'}
    outcome = ('FAILED' if entries and len(failures) == len(entries) else 'COMPLETED_WITH_ERRORS') if terminal and failures else campaign['status']
    return dict(scope='baseline_and_reference_jobs_only', outcome=outcome, jobs=rows,
                counts={state: sum(r['status'] == state for r in rows)
                        for state in ('queued', 'running', 'completed', 'failed', 'cancelled')},
                family_failures=failures, observed_at=now.isoformat(), eta_seconds=None,
                eta_reason='Remaining numeric/model/structural work is dynamic; reservations are not a task count.',
                stall_explanation='No persisted queue update for over 10 minutes. Suspected only; this does not prove worker death or cancel work.')
