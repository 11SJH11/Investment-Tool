"""Preregistered paired development windows. Labels are user-declared, never inferred from returns."""
from copy import deepcopy
from datetime import date
import json
from typing import Literal
from pydantic import Field
from .hypotheses import Strict
from .analysis import analyze, compare, digest
from . import candidate_checks
from .trials import Trials
from .repository import ResearchRepository

ACK='Run declared regime windows on development data; labels are my assumptions and windows are independent'


class Window(Strict):
    name: str = Field(min_length=1,max_length=80)
    start: date
    end: date
    definition: str = Field(min_length=1,max_length=2000)
    evidence_source: str = Field(min_length=1,max_length=1000)


class RegimeApproval(Strict):
    scenarios: list[Window] = Field(min_length=1,max_length=6)
    rationale: str = Field(min_length=1,max_length=4000)
    acknowledgement: Literal['Run declared regime windows on development data; labels are my assumptions and windows are independent']


def approve(database,project_id,candidate_id,payload):
    request=RegimeApproval.model_validate(payload).model_dump(mode='json')
    from .candidates import Candidates
    candidate=next((c for c in Candidates(database).list(project_id) if c['id']==candidate_id),None)
    if not candidate:raise ValueError('Unknown frozen candidate')
    baseline_params=candidate['snapshot']['hypothesis']['base_config'].get('strategy_params',{})
    def scenarios(base,request):
        result=[];seen=[]
        project=ResearchRepository(database).get(project_id)
        with database.connect() as c:datasets=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
        for w in request['scenarios']:
            if not base['start_date']<=w['start']<=w['end']<=base['end_date']:
                raise ValueError('Regime windows must be inside the frozen development range')
            if any(w['start']<=end and start<=w['end'] for start,end in seen):raise ValueError('Regime windows must not overlap')
            seen.append((w['start'],w['end']))
            scope={'symbols':base['symbols'],'start':w['start'],'end':w['end']}
            if any(ResearchRepository.overlap(scope,d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):raise ValueError('Holdout firewall blocked regime window')
            if not any(d['state'] in {'DEVELOPMENT','INSPECTED'} and set(base['symbols'])<=set(d['symbols']) and d['start']<=w['start'] and w['end']<=d['end'] for d in project['datasets']):raise ValueError('Development coverage required')
            for role,params in [('regime_baseline',baseline_params),('regime_candidate',base.get('strategy_params',{}))]:
                result.append({'name':w['name']+' / '+role.removeprefix('regime_'),'role':role,'overrides':{'start_date':w['start'],'end_date':w['end'],'strategy_params':deepcopy(params)}})
        return result
    return candidate_checks.approve(database,project_id,candidate_id,request,kind='regime',build_scenarios=scenarios)


def validate_identity(database,trial,payload,identity):
    if not identity:raise ValueError('Regime data identity required')
    index=payload['research_trial_cell'];pair=(index-1)//2
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=json.loads(c.execute('SELECT document FROM agent_trials WHERE id=?',(trial['id'],)).fetchone()[0])
        if current['status']!='ACTIVE':raise ValueError('Regime trial is no longer active')
        identities=current.setdefault('regime_data',{})
        previous=identities.get(str(pair))
        if previous is None:
            if index%2==0:raise ValueError('Regime baseline must establish data identity first')
            identities[str(pair)]=identity;current['revision']+=1
            c.execute('UPDATE agent_trials SET document=? WHERE id=?',(json.dumps(current),trial['id']))
        elif previous!=identity:raise ValueError('Regime pair data fingerprint changed')


def complete_cell(trial,cell,run,runs):
    identity=trial.get('regime_data',{}).get(str((cell['index']-1)//2))
    report=analyze(run)
    if not identity or report['data_fingerprint']!=identity or report['strategy_provenance']!=trial['hypothesis']['parent_source']:
        raise ValueError('Regime result identity changed')
    cell.update(status='COMPLETED',run_id=run['id'],analysis=report)
    if cell['role']=='regime_candidate':
        baseline=trial['cells'][cell['index']-1]
        if baseline['status']!='COMPLETED':raise ValueError('Regime baseline is not complete')
        comparison=compare(runs.get(baseline['run_id']),run)
        if not comparison['data_equivalent']:raise ValueError('Regime pair data mismatch')
        cell['comparison']=comparison


def evidence(connection,trial):
    approvals=[json.loads(r[0]) for r in connection.execute("SELECT detail FROM agent_events WHERE project_id=? AND action='candidate_regime_approved'",(trial['project_id'],))]
    approved=next((a for a in approvals if a.get('trial_id')==trial['id']),None)
    if not approved or approved['request_hash']!=digest(trial['regime_request']) or approved['candidate_hash']!=trial['candidate_hash']:raise ValueError('Regime approval changed')
    datasets=[json.loads(r[0]) for r in connection.execute('SELECT document FROM agent_datasets')]
    reports={};runs={};rows=[]
    for cell in trial['cells']:
        row={'name':cell['name'],'status':cell['status'],'run_id':cell.get('run_id')}
        if cell['status']=='COMPLETED':
            saved=connection.execute('SELECT config_json FROM backtest_runs WHERE id=?',(cell['run_id'],)).fetchone()
            if not saved:raise ValueError('Regime run unavailable')
            config=json.loads(saved[0]);expected=cell['payload']
            if any(config.get(k)!=v for k,v in expected.items() if k not in {'queue_job_id','save_run','experiment_group','test_role','run_name','run_notes','run_tags'}):raise ValueError('Regime configuration changed')
            scope={'symbols':config['symbols'],'start':config['start_date'],'end':config['end_date']}
            if any(ResearchRepository.overlap(scope,d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):raise ValueError('Holdout firewall blocked regime evidence')
            if not any(d['project_id']==trial['project_id'] and d['state'] in {'DEVELOPMENT','INSPECTED'} and set(scope['symbols'])<=set(d['symbols']) and d['start']<=scope['start'] and scope['end']<=d['end'] for d in datasets):raise ValueError('Regime evidence outside development data')
            result=json.loads(connection.execute('SELECT result_json FROM backtest_runs WHERE id=?',(cell['run_id'],)).fetchone()[0])
            run={'config':config,'result':result};report=analyze(run)
            recorded=cell['comparison']['child'] if not cell['index'] else cell['analysis']
            if digest(report)!=digest(recorded):raise ValueError('Regime saved evidence changed')
            expected_identity=trial['hypothesis']['data_fingerprint'] if not cell['index'] else trial.get('regime_data',{}).get(str((cell['index']-1)//2))
            if report['data_fingerprint']!=expected_identity or report['strategy_provenance']!=trial['hypothesis']['parent_source']:raise ValueError('Regime identity changed')
            row.update(summary=report['summary'],engine_metrics=report['engine_metrics'])
            runs[cell['index']]=run;reports[cell['index']]=report
            if cell['role']=='regime_candidate':
                comparison=compare(runs[cell['index']-1],run)
                if digest(comparison)!=digest(cell['comparison']):raise ValueError('Regime comparison changed')
                row['path']={k:comparison[k] for k in ('retained','removed','introduced','removed_winners','removed_large_winners')}
        rows.append(row)
    return {'trial_id':trial['id'],'status':trial['status'],'control_parity':trial['control_parity'],'request':trial['regime_request'],'rows':rows,
            'limitation':'User-declared development regimes, not automatically verified market classifications. Independent engine windows reset capital/positions and close at their end; no stitched portfolio performance, no automatic winner, no holdout validation.'}


def report(database,project_id,candidate_id):
    ResearchRepository(database).get(project_id)
    trial=next((t for t in Trials(database).list(project_id) if t.get('kind')=='regime' and t.get('candidate_id')==candidate_id),None)
    if not trial:return None
    with database.connect() as c:return evidence(c,trial)
