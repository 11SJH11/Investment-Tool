"""Read-only persisted development queue evidence, never holdout results."""
from datetime import datetime, timezone
import json


def baseline_progress(database, campaign, *, now=None):
    now = now or datetime.now(timezone.utc)
    entries = campaign.get('execution', {}).get('entries', [])
    keys = {('agent-baseline:' + e[field]): (e['family_id'], 'reference' if field == 'reference_project_id' else 'baseline')
            for e in entries for field in ('project_id', 'reference_project_id') if e.get(field)}
    rows = []
    trials = []
    with database.connect() as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_trials' AND type='table'").fetchone():
            for entry in entries:
                if not entry.get('project_id'):
                    continue
                for raw in c.execute('SELECT document FROM agent_trials WHERE project_id=? ORDER BY rowid', (entry['project_id'],)):
                    trial = json.loads(raw[0])
                    cells = []
                    for cell in trial['cells']:
                        # Match the queue's immutable request key for the current attempt only.
                        key = f"agent-trial:{trial['id']}:{cell['index']}:{cell['attempt']}"
                        keys[key] = (entry['family_id'], 'numeric_' + cell['role'])
                        cells.append({name: cell.get(name) for name in ('index','role','attempt','status','job_id')})
                    trials.append(dict(id=trial['id'], family_id=entry['family_id'], status=trial['status'], cells=cells))
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='backtest_jobs' AND type='table'").fetchone():
            for key, (family, role) in keys.items():
                for raw in c.execute('''SELECT id,status,processed,total,run_id,error,created_at,updated_at
                        FROM backtest_jobs WHERE request_key=? ORDER BY ordinal''', (key,)):
                    row = dict(raw)
                    row.update(family_id=family, role=role)
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
    return dict(scope='baseline_reference_and_current_numeric_attempts', outcome=outcome, jobs=rows, numeric_trials=trials,
                counts={state: sum(r['status'] == state for r in rows)
                        for state in ('queued', 'running', 'completed', 'failed', 'cancelled')},
                family_failures=failures, observed_at=now.isoformat(), eta_seconds=None,
                eta_reason='Remaining model/structural work is dynamic; reservations are not a task count.',
                stall_explanation='No persisted queue update for over 10 minutes. Suspected only; this does not prove worker death or cancel work.')
