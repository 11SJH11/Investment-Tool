"""Baseline queue integration; reuses existing idempotent BacktestJobs."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
import json
from app.backtesting.strategies import strategy_registry
from .repository import ResearchRepository
from .access import scope,check


def validate_submission(database,payload):
    if payload.get('research_validation_id'):
        from .validation import validate
        validate(database,payload)
        return
    if payload.get('research_trial_id'):
        from .trials import validate
        validate(database,payload)
        return
    project=ResearchRepository(database).get(payload['research_project_id'])
    if project['state'] in {'PAUSED','ARCHIVED','FAILED'}:raise ValueError('Research is not active')
    submitted={k:v for k,v in payload.items() if k!='queue_job_id'}
    if submitted!=project.get('baseline_payload'):raise ValueError('Backtest payload differs from the approved frozen research baseline')
    if project['strategy_provenance']!=strategy_registry.provenance(project['strategy_key']):raise ValueError('Strategy source changed after project creation; create a new lineage project')

def start(services,id,payload):
    repo=ResearchRepository(services.database);project=repo.get(id)
    if payload['strategy_key']!=project['strategy_key']:raise ValueError('Baseline strategy must match the project')
    symbols=payload['symbols']
    if isinstance(symbols,str):symbols=symbols.replace(',',' ').split()
    if len(symbols)!=1:raise ValueError('Initial research projects run one symbol with independent capital')
    payload={**payload,'symbols':[symbols[0].strip().upper()],'save_run':True,'research_project_id':id,'research_experiment':None}
    if project['strategy_provenance']!=strategy_registry.provenance(project['strategy_key']):raise ValueError('Strategy source changed; create a new project')
    if project.get('baseline_payload') and project['baseline_payload']!=payload:raise ValueError('Baseline configuration is frozen')
    if project['state'] not in {'CREATED','BASELINE_PENDING','BASELINE_RUNNING'}:raise ValueError('Baseline already inspected or project is not active')
    zone=ZoneInfo('America/New_York')
    begin=datetime.combine(datetime.fromisoformat(payload['start_date']).date(),time.min,tzinfo=zone)
    end=datetime.combine(datetime.fromisoformat(payload['end_date']).date()+timedelta(days=1),time.min,tzinfo=zone)
    with scope(services.database,id):check(symbols[0],payload['primary_timeframe'],begin,end)
    with services.database.connect() as c:
        c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone();current=json.loads(row[0])
        if current.get('baseline_payload') not in (None,payload):raise ValueError('Concurrent baseline configuration changed')
        if current['state'] not in {'CREATED','BASELINE_PENDING','BASELINE_RUNNING'}:raise ValueError('Project changed during submission')
        current.update(baseline_payload=payload,state='BASELINE_PENDING',baseline_request_key=current.get('baseline_request_key') or 'agent-baseline:'+id)
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(current),id))
    jobs=services.backtest_jobs.enqueue([payload],current['baseline_request_key'])
    with services.database.connect() as c:
        c.execute('BEGIN IMMEDIATE');current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()[0])
        current['baseline_job_id']=jobs[0]['id']
        if current['state']=='BASELINE_PENDING':current['state']='BASELINE_RUNNING'
        c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(current),id))
    return observe(services,id)

def observe(services,id):
    repo=ResearchRepository(services.database);project=repo.get(id)
    if project['state'] not in {'BASELINE_PENDING','BASELINE_RUNNING'}:return project
    job_id=project.get('baseline_job_id')
    if not job_id:return project  # repeat Start recovers the durable idempotency key
    try:job=services.backtest_jobs.get(job_id)
    except ValueError:
        job={'status':'failed','error':'Queue record was removed; no automatic resubmission was attempted.'}
    if job['status']=='completed':return repo.inspect_run(id,job['run_id'])
    if job['status'] in {'failed','cancelled'}:
        with services.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()[0])
            if current['state'] in {'BASELINE_PENDING','BASELINE_RUNNING'}:
                current.update(state='PAUSED',last_error=job.get('error') or 'Baseline cancelled')
                c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(current),id))
        return repo.get(id)
    return {**project,'job':job}
