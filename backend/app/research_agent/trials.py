"""Approved, bounded development trials. Existing queue and engine own all simulations."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from threading import Event, Thread, RLock
from uuid import uuid4
from app.backtesting.strategies import strategy_registry
from app.market_concepts import registry as concepts
from app.services.research_experiments import children
from app.storage.backtest_run_repository import BacktestRunRepository
from .analysis import compare, digest
from .hypotheses import Budget, HypothesisRepository
from .repository import ResearchRepository


def now():return datetime.now(timezone.utc).timestamp()

def request_key(trial, cell):return 'agent-trial:'+trial['id']+':'+str(cell['index'])+':'+str(cell['attempt'])


def remaining(trial):
    return max(0, trial['remaining_seconds']-max(0,now()-trial['active_since'])) if trial['status']=='ACTIVE' else trial['remaining_seconds']


class Trials:
    def __init__(self, database):
        self.database=database
        ResearchRepository(database)
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_trials(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, hypothesis_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL)')

    def list(self, project_id=None):
        with self.database.connect() as c:
            query='SELECT document FROM agent_trials'+(' WHERE project_id=?' if project_id else '')+' ORDER BY rowid'
            return [json.loads(r[0]) for r in c.execute(query,(project_id,) if project_id else ())]

    def get(self, id):
        with self.database.connect() as c:
            row=c.execute('SELECT document FROM agent_trials WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Unknown research trial')
            return json.loads(row[0])

    def approve(self, project_id, hypothesis_id, *, loop_id=None):
        hypothesis=next((h for h in HypothesisRepository(self.database).list(project_id) if h['id']==hypothesis_id),None)
        if not hypothesis:raise ValueError('Unknown preregistered hypothesis')
        project=ResearchRepository(self.database).get(project_id)
        if project['state']!='BASELINE_ANALYSIS':raise ValueError('Research project is not active')
        check_source(hypothesis)
        base=deepcopy(hypothesis['base_config'])
        for key in ('queue_job_id','research_project_id','research_trial_id','research_trial_cell','research_experiment','research_parent_id','market_data_fingerprint','strategy_provenance','workspace'):
            base.pop(key,None)
        trial_id=str(uuid4())
        plan, variants=children(base,hypothesis['axes'],'agent:'+trial_id,name='Research development',role='development')
        if plan!=hypothesis['plan']:raise ValueError('Preregistered experiment definition changed')
        payloads=[base,*variants]
        cells=[]
        for index,payload in enumerate(payloads):
            payload.update(save_run=True,research_project_id=project_id,research_trial_id=trial_id,research_trial_cell=index)
            cells.append({'index':index,'role':'control' if index==0 else 'variant','attempt':0,'status':'PENDING','payload':payload})
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if loop_id:
                from .loop import require_active
                require_active(c,project_id,loop_id)
            existing=c.execute('SELECT document FROM agent_trials WHERE hypothesis_id=?',(hypothesis_id,)).fetchone()
            if existing:return json.loads(existing[0])
            current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if current['state']!='BASELINE_ANALYSIS':raise ValueError('Research project is not active')
            others=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(project_id,))]
            if any(t['status']=='ACTIVE' for t in others):raise ValueError('One approved development trial may run at a time')
            budget=Budget.model_validate(current.get('research_budget',{}))
            from .validation import reserved
            if sum(t['reserved_runs'] for t in others)+reserved(c,project_id)+len(cells)>budget.max_trial_runs:raise ValueError('Trial simulation budget exhausted')
            trial={'loop_id':loop_id,'id':trial_id,'project_id':project_id,'hypothesis_id':hypothesis_id,'status':'ACTIVE','revision':0,
                   'created_at':datetime.now(timezone.utc).isoformat(),'active_since':now(),'remaining_seconds':budget.max_trial_minutes*60,
                   'reserved_runs':len(cells),'parent_run_id':hypothesis['parent_run_id'],'hypothesis':hypothesis,'cells':cells,
                   'verdict':'PENDING_CONTROL','control_parity':None}
            c.execute('INSERT INTO agent_trials VALUES (?,?,?,?)',(trial_id,project_id,hypothesis_id,json.dumps(trial,allow_nan=False)))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'development_trial_approved',json.dumps({'trial_id':trial_id,'reserved_runs':len(cells)})))
        return trial

    def save_active(self, trial):
        # Do not overwrite a concurrent pause/resume or another coordinator update.
        revision=trial['revision'];trial['revision']+=1
        with self.database.connect() as c:
            changed=c.execute("UPDATE agent_trials SET document=? WHERE id=? AND json_extract(document,'$.revision')=? AND json_extract(document,'$.status')='ACTIVE'",(json.dumps(trial,allow_nan=False),trial['id'],revision)).rowcount
        return bool(changed)

    def transition(self,id,action,jobs):
        trial=self.get(id)
        if action not in {'pause','resume','cancel'}:raise ValueError('Unknown trial action')
        # Resolve queue state outside a write transaction: queue owns its own locks.
        cell=next((c for c in trial['cells'] if c['status']!='COMPLETED'),None)
        job=lookup_job(self.database,request_key(trial,cell)) if cell else None
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current=json.loads(c.execute('SELECT document FROM agent_trials WHERE id=?',(id,)).fetchone()[0])
            if current['revision']!=trial['revision']:raise ValueError('Trial advanced; refresh and retry the action')
            if action=='resume':
                if trial['status']!='PAUSED' or trial['remaining_seconds']<=0:raise ValueError('Only paused trials with time remaining can resume')
                project=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(trial['project_id'],)).fetchone()[0])
                if project['state']!='BASELINE_ANALYSIS':raise ValueError('Resume the project first')
                check_source(trial['hypothesis'])
                if trial.get('kind') in {'cost','simplification','regime'}:
                    from .candidate_checks import verify_candidate
                    verify_candidate(self.database,trial)
                if c.execute("SELECT 1 FROM agent_trials WHERE project_id=? AND id!=? AND json_extract(document,'$.status')='ACTIVE'",(trial['project_id'],id)).fetchone():raise ValueError('Another trial is active')
                if job and job['status'] not in {'completed','failed','cancelled'}:raise ValueError('Wait for the old queue job to stop')
                if cell and ((job and job['status']!='completed') or (not job and cell.get('job_id'))):
                    used=sum(json.loads(r[0])['reserved_runs'] for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(trial['project_id'],)))
                    from .validation import reserved
                    used+=reserved(c,trial['project_id'])
                    if used+1>Budget.model_validate(project.get('research_budget',{})).max_trial_runs:raise ValueError('Trial simulation budget exhausted')
                    trial['reserved_runs']+=1;cell['attempt']+=1;cell['status']='PENDING';cell.pop('error',None);cell.pop('job_id',None)
                trial.update(status='ACTIVE',active_since=now());trial.pop('error',None)
            else:
                if trial['status'] not in {'ACTIVE','PAUSED'}:raise ValueError('Trial is terminal')
                trial.update(remaining_seconds=remaining(trial),status='PAUSED' if action=='pause' else 'CANCELLED')
            trial['revision']+=1
            c.execute('UPDATE agent_trials SET document=? WHERE id=?',(json.dumps(trial),id))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(trial['project_id'],'trial_'+action,json.dumps({'trial_id':id})))
        if action!='resume' and job:jobs.cancel(job['id'])
        return trial


def lookup_job(database,key):
    with database.connect() as c:
        row=c.execute('SELECT id,status,run_id,error FROM backtest_jobs WHERE request_key=? ORDER BY ordinal LIMIT 1',(key,)).fetchone()
        return dict(row) if row else None


def check_source(hypothesis):
    key=hypothesis['base_config']['strategy_key']
    if strategy_registry.provenance(key)!=hypothesis['parent_source']:raise ValueError('Frozen strategy source changed')
    spec=next(s for s in strategy_registry.specs() if s.key==key)
    if concepts.declarations(spec.concepts)!=hypothesis['parent_concepts']:raise ValueError('Frozen concept source changed')


def active(database,payload):
    with database.connect() as c:
        row=c.execute('SELECT document FROM agent_trials WHERE id=?',(payload['research_trial_id'],)).fetchone()
        project=c.execute('SELECT document FROM agent_projects WHERE id=?',(payload.get('research_project_id'),)).fetchone()
    if not row or not project:return False
    trial=json.loads(row[0])
    if trial.get('loop_id'):
        from .loop import require_active
        try:
            with database.connect() as c:require_active(c,trial['project_id'],trial['loop_id'])
        except ValueError:return False
    return trial['status']=='ACTIVE' and remaining(trial)>0 and json.loads(project[0])['state']=='BASELINE_ANALYSIS'


def validate(database,payload):
    repo=Trials(database);trial=repo.get(payload['research_trial_id'])
    if payload.get('research_project_id')!=trial['project_id'] or not active(database,payload):raise ValueError('Development trial is not active')
    index=payload.get('research_trial_cell')
    if type(index) is not int or not 0<=index<len(trial['cells']):raise ValueError('Unknown trial cell')
    cell=trial['cells'][index]
    if {k:v for k,v in payload.items() if k!='queue_job_id'}!=cell['payload']:raise ValueError('Payload differs from approved trial')
    if index and trial['control_parity'] is not True:raise ValueError('Control parity is required before variants')
    job=lookup_job(database,request_key(trial,cell))
    if not job or job['id']!=payload.get('queue_job_id'):raise ValueError('Job is not the approved trial attempt')
    check_source(trial['hypothesis'])
    if trial.get('kind') in {'cost','simplification','regime'}:
        from .candidate_checks import verify_candidate
        verify_candidate(database,trial)
    return trial


def validate_data(database,payload,identity):
    trial=validate(database,payload)
    if trial.get('kind')=='regime' and payload['research_trial_cell']:
        from .regimes import validate_identity
        validate_identity(database,trial,payload,identity)
    elif not identity or identity!=trial['hypothesis']['data_fingerprint']:raise ValueError('Frozen research data fingerprint changed')


class TrialCoordinator:
    def __init__(self,jobs):
        self.jobs=jobs;self.repo=Trials(jobs.database);self.lock=RLock();self.stop=Event()
        self.thread=Thread(target=self._loop,name='research-trials',daemon=True);self.thread.start()

    def close(self):self.stop.set();self.thread.join(timeout=10)

    def _loop(self):
        while not self.stop.wait(.5):
            try:self.tick()
            except Exception:
                # Never emit raw provider/strategy exceptions from the supervisor.
                # A later tick can recover transient database contention without duplicate submission.
                continue

    def tick(self):
        with self.lock:
            from .validation import Validations
            Validations(self.jobs.database).tick(self.jobs)
            for trial in self.repo.list():
                if trial['status']!='ACTIVE':continue
                try:self._advance(trial)
                except Exception:
                    trial.update(remaining_seconds=remaining(trial),status='PAUSED',error='Trial coordination failed. Inspect saved jobs; resume explicitly.')
                    self.repo.save_active(trial)

    def _advance(self,trial):
        project=ResearchRepository(self.jobs.database).get(trial['project_id'])
        cell=next((c for c in trial['cells'] if c['status']!='COMPLETED'),None)
        authorized=True
        if trial.get('loop_id'):
            from .loop import require_active
            try:
                with self.jobs.database.connect() as c:require_active(c,trial['project_id'],trial['loop_id'])
            except ValueError:authorized=False
        if not authorized or project['state']!='BASELINE_ANALYSIS' or remaining(trial)<=0:
            trial.update(remaining_seconds=remaining(trial),status='PAUSED' if remaining(trial)>0 else 'BUDGET_EXHAUSTED',error='Project paused/archived or active-time budget exhausted')
            self.repo.save_active(trial)
            if cell:
                job=lookup_job(self.jobs.database,request_key(trial,cell))
                if job:self.jobs.cancel(job['id'])
            return
        if cell is None:
            trial.update(status='COMPLETED',verdict='DEVELOPMENT_REVIEW_REQUIRED');self.repo.save_active(trial);return
        check_source(trial['hypothesis'])
        key=request_key(trial,cell);job=lookup_job(self.jobs.database,key)
        if not job:
            if cell.get('job_id'):raise ValueError('Queue record removed; no silent resubmission')
            if cell['index'] and trial['control_parity'] is not True:raise ValueError('Control not verified')
            job=self.jobs.enqueue([cell['payload']],key)[0]
        cell.update(job_id=job['id'],status=job['status'].upper())
        if job['status']=='completed':
            runs=BacktestRunRepository(self.jobs.database)
            run=runs.get(job['run_id']);parent=runs.get(trial['parent_run_id'])
            if run['config'].get('research_trial_id')!=trial['id'] or run['config'].get('research_trial_cell')!=cell['index']:raise ValueError('Saved result has wrong trial provenance')
            if trial.get('kind')=='regime' and cell['index']:
                from .regimes import complete_cell
                complete_cell(trial,cell,run,runs)
                self.repo.save_active(trial)
                return
            comparison=compare(parent,run)
            cell.update(status='COMPLETED',run_id=job['run_id'],comparison=comparison)
            if not comparison['data_equivalent']:raise ValueError('Data mismatch')
            if cell['role']=='control':
                trial['control_parity']=comparison['control_parity']
                if not trial['control_parity']:
                    trial.update(status='FAILED',verdict='CONTROL_MISMATCH',error='Control did not reproduce frozen baseline; no variants released')
            else:trial['verdict']='DEVELOPMENT_REVIEW_REQUIRED'
        elif job['status'] in {'failed','cancelled'}:
            cell['error']=job.get('error') or 'Cancelled'
            trial.update(remaining_seconds=remaining(trial),status='PAUSED',error='Queue attempt stopped; explicit resume required')
        self.repo.save_active(trial)
