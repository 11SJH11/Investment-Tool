"""Shared bounded candidate checks; the existing trial queue owns execution."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from uuid import uuid4
from .hypotheses import Budget
from .analysis import compare, digest
from .candidates import Candidates
from .trials import Trials, now, check_source
from .repository import ResearchRepository

COSTS = ('commission_per_order', 'spread_bps', 'slippage_bps')


def verify_candidate(database, trial):
    from .decisions import require_undecided
    with database.connect() as c:
        row = c.execute('SELECT document FROM agent_candidates WHERE id=? AND project_id=?', (trial['candidate_id'], trial['project_id'])).fetchone()
    candidate = json.loads(row[0]) if row else None
    if not candidate or digest(candidate['snapshot']) != trial['candidate_hash']:
        raise ValueError('Candidate trial evidence changed')
    with database.connect() as c:
        require_undecided(c, candidate['id'])


def approve(database, project_id, candidate_id, request, *, kind, build_scenarios):
    if kind not in {'cost', 'simplification', 'regime'}:raise ValueError('Unknown candidate check')
    request_field = kind + '_request'
    trials = Trials(database)
    # One preregistered plan per check kind and candidate. No result-driven replacement of scenarios.
    previous = next((t for t in trials.list(project_id) if t.get('candidate_id') == candidate_id and t.get('kind') == kind), None)
    if previous:
        if previous[request_field] != request:
            raise ValueError('Candidate check plan is immutable')
        return previous
    candidates = Candidates(database)
    candidate = next((c for c in candidates.list(project_id) if c['id'] == candidate_id), None)
    if not candidate or digest(candidate['snapshot']) != candidate['snapshot_hash']:
        raise ValueError('Valid frozen candidate required')
    _, cell, _ = candidates.assess(project_id, candidate['trial_id'], candidate['cell_index'])
    if cell['payload'] != candidate['snapshot']['configuration'] or cell['comparison']['child']['result_digest'] != candidate['snapshot']['result_digest']:
        raise ValueError('Frozen candidate no longer matches the verified trial')
    base = deepcopy(candidate['snapshot']['configuration'])
    for key in ('queue_job_id', 'research_trial_id', 'research_trial_cell', 'research_experiment', 'research_parent_id', 'market_data_fingerprint', 'strategy_provenance', 'workspace'):
        base.pop(key, None)
    if len({s['name'] for s in request['scenarios']}) != len(request['scenarios']):
        raise ValueError('Scenario names must be unique')
    scenarios = build_scenarios(base, request)
    identifier = str(uuid4())
    cells = []
    for index, scenario in enumerate([None, *scenarios]):
        config = deepcopy(base)
        if scenario:
            config.update(deepcopy(scenario['overrides']))
        config.update(save_run=True, test_role='development', research_project_id=project_id, research_trial_id=identifier, research_trial_cell=index)
        cells.append(dict(index=index, role=scenario.get('role', 'stress' if kind=='cost' else 'ablation') if scenario else 'control', name=scenario['name'] if scenario else 'Frozen candidate control', attempt=0, status='PENDING', payload=config))
    hypothesis = deepcopy(candidate['snapshot']['hypothesis'])
    hypothesis.update(base_config=base, description={'cost':'Candidate execution cost stress','simplification':'Candidate single-rule simplification','regime':'Declared development regime windows'}[kind], data_fingerprint=candidate['snapshot']['data_fingerprint'])
    check_source(hypothesis)
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        rows = [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?', (project_id,))]
        old = next((t for t in rows if t.get('kind') == kind and t.get('candidate_id') == candidate_id), None)
        if old:
            if old[request_field] != request:raise ValueError('Candidate check plan is immutable')
            return old
        from .decisions import require_undecided
        from .validation import reserved
        require_undecided(c, candidate_id)
        project = json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?', (project_id,)).fetchone()[0])
        if project['state'] != 'BASELINE_ANALYSIS':raise ValueError('Research project must be active')
        if any(t['status'] == 'ACTIVE' for t in rows):raise ValueError('Finish or pause active trials first')
        budget = Budget.model_validate(project.get('research_budget', {}))
        if sum(t['reserved_runs'] for t in rows) + reserved(c, project_id) + len(cells) > budget.max_trial_runs:
            raise ValueError('Trial simulation budget exhausted')
        trial = dict(id=identifier, project_id=project_id, hypothesis_id=kind+':'+candidate_id, kind=kind, candidate_id=candidate_id,
            candidate_hash=candidate['snapshot_hash'], status='ACTIVE', revision=0,
            created_at=datetime.now(timezone.utc).isoformat(), active_since=now(), remaining_seconds=budget.max_trial_minutes*60,
            reserved_runs=len(cells), parent_run_id=candidate['run_id'], hypothesis=hypothesis, cells=cells,
            verdict='PENDING_CONTROL', control_parity=None)
        trial[request_field] = request
        c.execute('INSERT INTO agent_trials VALUES (?,?,?,?)', (identifier, project_id, trial['hypothesis_id'], json.dumps(trial, allow_nan=False)))
        c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)', (project_id, 'candidate_'+kind+'_approved', json.dumps({'trial_id':identifier, 'candidate_hash':candidate['snapshot_hash'], 'request_hash':digest(request)})))
    return trial


def money(trades):
    from .diagnostics import number
    return {field: sum(t[field] for t in trades) if all(number(t.get(field)) is not None for t in trades) else None for field in ('gross_pnl', 'fees', 'net_pnl')}


def evidence(connection, trial):
    """Reverify saved evidence, retaining all scenarios, including failures and missing results."""
    kind = trial['kind']
    approvals = [json.loads(r[0]) for r in connection.execute("SELECT detail FROM agent_events WHERE project_id=? AND action=?", (trial['project_id'], 'candidate_'+kind+'_approved'))]
    approved = next((a for a in approvals if a.get('trial_id') == trial['id']), None)
    if not approved or approved.get('request_hash') != digest(trial[kind+'_request']) or approved.get('candidate_hash') != trial['candidate_hash']:
        raise ValueError('Approved candidate check plan changed')
    def saved_run(run_id, expected_params):
        row = connection.execute('SELECT config_json FROM backtest_runs WHERE id=?', (run_id,)).fetchone()
        if not row:raise ValueError('Candidate check saved run was deleted')
        config = json.loads(row[0])
        base = trial['hypothesis']['base_config']
        if any(config.get(k) != base.get(k) for k in ('symbols','start_date','end_date','primary_timeframe','strategy_key')):
            raise ValueError('Candidate check development scope changed')
        if config.get('strategy_params', {}) != expected_params:raise ValueError('Candidate check parameters changed')
        datasets = [json.loads(r[0]) for r in connection.execute('SELECT document FROM agent_datasets')]
        scope = dict(symbols=config['symbols'], start=config['start_date'], end=config['end_date'])
        if any(ResearchRepository.overlap(scope,d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):
            raise ValueError('Holdout firewall blocked candidate evidence')
        if not any(d['project_id']==trial['project_id'] and d['state'] in {'DEVELOPMENT','INSPECTED'} and set(scope['symbols'])<=set(d['symbols']) and d['start']<=scope['start'] and scope['end']<=d['end'] for d in datasets):
            raise ValueError('Candidate evidence must remain on development data')
        result = connection.execute('SELECT result_json FROM backtest_runs WHERE id=?', (run_id,)).fetchone()
        return {'config':config, 'result':json.loads(result[0])}
    parent = saved_run(trial['parent_run_id'], trial['hypothesis']['base_config'].get('strategy_params', {}))
    rows = []
    for cell in trial['cells']:
        row = dict(name=cell['name'], status=cell['status'], run_id=cell.get('run_id'), costs={k:cell['payload'].get(k, 0) for k in COSTS})
        row['parameters'] = cell['payload'].get('strategy_params', {})
        if cell['status'] == 'COMPLETED':
            run = saved_run(cell['run_id'], cell['payload'].get('strategy_params', {}))
            config = run['config']
            expected = cell['payload']
            fields = (*COSTS, 'research_trial_id', 'research_trial_cell', 'symbols', 'start_date', 'end_date', 'strategy_key', 'strategy_params')
            if any(config.get(k) != expected.get(k) for k in fields):raise ValueError('Candidate check configuration changed')
            comparison = compare(parent, run)
            if digest(comparison) != digest(cell['comparison']) or not comparison['data_equivalent'] or comparison['parent']['data_fingerprint'] != trial['hypothesis']['data_fingerprint'] or comparison['child']['strategy_provenance'] != trial['hypothesis']['parent_source']:
                raise ValueError('Candidate check saved evidence changed')
            row.update(summary=comparison['child']['summary'], money=money(run['result'].get('trades', [])),
                engine_metrics=comparison['child']['engine_metrics'], changed_retained=comparison['changed_retained'],
                removed=comparison['removed'], introduced=comparison['introduced'], removed_winners=comparison['removed_winners'], removed_large_winners=comparison['removed_large_winners'], retained=comparison['retained'])
        rows.append(row)
    return dict(kind=kind, request=trial[kind+'_request'], trial_id=trial['id'], status=trial['status'], control_parity=trial['control_parity'], rows=rows,
        limitation=('Development engine reruns under declared costs; not measured broker costs, latency simulation, regime validation or automatic acceptance.' if kind=='cost' else 'Development single-parameter ablations. Off semantics are user-declared, not proven by Ledger. No automatic winner, combined-rule inference or validation.'))


def report(database, project_id, candidate_id, *, kind):
    ResearchRepository(database).get(project_id)
    trial = next((t for t in Trials(database).list(project_id) if t.get('kind') == kind and t.get('candidate_id') == candidate_id), None)
    if not trial:return None
    with database.connect() as c:return evidence(c, trial)
