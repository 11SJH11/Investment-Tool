"""Bounded development-trial evidence, reverified before sending it to a model."""
import json
from app.storage.backtest_run_repository import BacktestRunRepository
from .analysis import compare, digest
from .trials import Trials, check_source


SUMMARY = ('n', 'average_r', 'total_r', 'profit_factor_r', 'win_rate_pct', 'low_sample')


def compact(summary):
    return {key: summary.get(key) for key in SUMMARY}


def development_feedback(database, project, *, trial_id=None):
    evidence = {}
    trials = [t for t in Trials(database).list(project['id']) if t.get('kind') not in {'cost','simplification','regime'}]
    completed = [t for t in trials if t['status'] == 'COMPLETED']
    # Chronological selection, never select by profitability. No partial trial is shown.
    selected = [t for t in completed if t["id"]==trial_id] if trial_id else completed[-2:]
    if trial_id and not selected:raise ValueError("Completed development trial required")
    runs = BacktestRunRepository(database)
    for trial in selected:
        hypothesis = trial['hypothesis']
        check_source(hypothesis)
        if trial['parent_run_id'] != project['baseline_run_id'] or trial['control_parity'] is not True:
            raise ValueError('Trial feedback requires the frozen baseline and verified control')
        base = hypothesis['base_config']
        if not any(d['state'] in {'DEVELOPMENT','INSPECTED'} and set(base['symbols']) <= set(d['symbols']) and d['start'] <= base['start_date'] and base['end_date'] <= d['end'] for d in project['datasets']):
            raise ValueError('Trial feedback must remain on development data')
        cells = []
        parent = runs.get(trial['parent_run_id'])
        for cell in trial['cells']:
            # Validate dates and ownership from metadata before touching result JSON.
            with database.connect() as c:
                row = c.execute('SELECT config_json FROM backtest_runs WHERE id=?', (cell.get('run_id'),)).fetchone()
            if not row: raise ValueError('Trial feedback run was deleted')
            config = json.loads(row[0])
            if (config.get('research_trial_id') != trial['id'] or config.get('research_trial_cell') != cell['index'] or
                    any(config.get(k) != base.get(k) for k in ('symbols','start_date','end_date','primary_timeframe','strategy_key')) or
                    config.get('strategy_params',{}) != cell['payload'].get('strategy_params',{})):
                raise ValueError('Trial feedback run identity or development scope changed')
            comparison = compare(parent, runs.get(cell['run_id']))
            if not comparison['data_equivalent'] or comparison['child']['strategy_provenance'] != hypothesis['parent_source']:
                raise ValueError('Trial feedback source or data identity changed')
            if digest(comparison) != digest(cell['comparison']):
                raise ValueError('Trial feedback saved results changed')
            child = comparison['child']
            cells.append({'cell':cell['index'], 'role':cell['role'], 'run_id':cell['run_id'],
                'parameters':{a['parameter']:cell['payload']['strategy_params'].get(a['parameter']) for a in hypothesis['axes']},
                'summary':compact(child['summary']),
                'retained':comparison['retained'], 'changed_retained':comparison['changed_retained'],
                **{key:compact(comparison[key]) for key in ('removed','introduced','removed_winners','removed_losers','removed_large_winners','removed_session_close_winners','retained_parent','retained_child')},
                'year':{k:compact(v) for k,v in sorted(child['breakdowns'].get('year',{}).items())},
                'concentration':child['concentration']})
        evidence['trial/'+trial['id']] = {'hypothesis_id':hypothesis['id'], 'expected_result':hypothesis['expected_result'],
            'falsification':hypothesis['falsification'], 'axes':hypothesis['axes'], 'control_parity':True, 'cells':cells,
            'interpretation':'Development only. Review all cells, winner loss and path changes; no automatic winner or promotion.'}
    return evidence, {'completed_trials':len(completed), 'included_trials':len(selected), 'omitted_trials':len(completed)-len(selected),
        'selection':'Latest two completed trials, chronological, all cells. Earlier trials remain in Ledger.',
        'incomplete_trials':sum(t['status'] != 'COMPLETED' for t in trials)}
