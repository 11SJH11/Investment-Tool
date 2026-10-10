"""Candidate-bound, explicitly approved validation via the existing queue."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import json
from pydantic import Field
from .hypotheses import Strict, Budget
from .candidates import Candidates
from .repository import ResearchRepository
from .trials import check_source, lookup_job, now
from .analysis import analyze, compare, digest
from app.storage.backtest_run_repository import BacktestRunRepository


class Criteria(Strict):
    minimum_trades: int = Field(default=30,ge=1,le=100000,strict=True)
    minimum_average_r: float = Field(default=0,ge=-100,le=100)
    minimum_profit_factor_r: float = Field(default=1,ge=0,le=100)


def reserved(connection,project_id):
    total=0
    for table in ('agent_validations','agent_sandbox_runs'):
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            total+=sum(json.loads(r[0])['reserved_runs'] for r in connection.execute('SELECT document FROM '+table+' WHERE project_id=?',(project_id,)))
    return total


def key(document,index):return 'agent-validation:'+document['id']+':'+str(index)


def verdict(summary,criteria):
    if summary['n']<criteria['minimum_trades'] or any(summary.get(k) is None for k in ('average_r','profit_factor_r')):
        return 'INSUFFICIENT_EVIDENCE'
    return 'VALIDATION_PASS' if summary['average_r']>=criteria['minimum_average_r'] and summary['profit_factor_r']>=criteria['minimum_profit_factor_r'] else 'VALIDATION_FAIL'


class Validations:
    def __init__(self,database):
        self.database=database;self.candidates=Candidates(database)
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_validations(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,candidate_id TEXT NOT NULL UNIQUE,document TEXT NOT NULL)')

    def list(self,project_id=None):
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_validations'+(' WHERE project_id=?' if project_id else '')+' ORDER BY rowid',(project_id,) if project_id else ())]

    def get(self,id):
        with self.database.connect() as c:
            row=c.execute('SELECT document FROM agent_validations WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Unknown validation grant')
            return json.loads(row[0])

    def approve(self,project_id,candidate_id,dataset_id,criteria):
        criteria=Criteria.model_validate(criteria).model_dump()
        existing=next((v for v in self.list(project_id) if v['candidate_id']==candidate_id),None)
        if existing:
            if existing['dataset_id']!=dataset_id or existing['criteria']!=criteria:raise ValueError('Validation grant is immutable')
            return existing
        candidate=next((x for x in self.candidates.list(project_id) if x['id']==candidate_id),None)
        if not candidate or candidate['state']!='FROZEN':raise ValueError('Frozen candidate required')
        if digest(candidate['snapshot'])!=candidate['snapshot_hash']:raise ValueError('Frozen candidate snapshot changed')
        trial,cell,_=self.candidates.assess(project_id,candidate['trial_id'],candidate['cell_index'])
        if candidate['snapshot']['configuration']!=cell['payload'] or candidate['snapshot']['result_digest']!=cell['comparison']['child']['result_digest']:
            raise ValueError('Frozen candidate no longer matches the verified trial')
        project=ResearchRepository(self.database).get(project_id)
        dataset=next((d for d in project['datasets'] if d['id']==dataset_id),None)
        config=candidate['snapshot']['configuration']
        if not dataset or dataset['state'] not in {'LOCKED_HOLDOUT','FUTURE_OOS'}:raise ValueError('Select an untouched dataset belonging to this project')
        if dataset['timeframe']!=config['primary_timeframe'] or set(dataset['symbols'])!=set(config['symbols']):raise ValueError('Validation symbol/timeframe must match the frozen candidate')
        id=str(uuid4());cells=[]
        for index,original in enumerate((candidate['snapshot']['hypothesis']['base_config'],config)):
            payload=deepcopy(original)
            for field in ('queue_job_id','research_trial_id','research_trial_cell','research_experiment','research_parent_id','market_data_fingerprint','strategy_provenance','workspace'):
                payload.pop(field,None)
            payload.update(test_role='validation',start_date=dataset['start'],end_date=dataset['end'],save_run=True,research_project_id=project_id,research_validation_id=id,research_validation_cell=index)
            cells.append({'index':index,'role':'baseline' if index==0 else 'candidate','status':'PENDING','payload':payload})
        budget=Budget.model_validate(project.get('research_budget',{}))
        document={'id':id,'project_id':project_id,'candidate_id':candidate_id,'candidate_hash':candidate['snapshot_hash'],
            'dataset_id':dataset_id,'dataset':deepcopy(dataset),'criteria':criteria,'candidate':candidate,'cells':cells,
            'status':'ACTIVE','revision':0,'reserved_runs':2,'created_at':datetime.now(timezone.utc).isoformat(),
            'deadline':now()+budget.max_trial_minutes*60,'data_fingerprint':None,'verdict':'PENDING','automatic_promotion':False}
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT document FROM agent_validations WHERE candidate_id=?',(candidate_id,)).fetchone()
            if prior:
                old=json.loads(prior[0])
                if old['dataset_id']!=dataset_id or old['criteria']!=criteria:raise ValueError('Validation grant is immutable')
                return old
            current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if current['state']!='BASELINE_ANALYSIS':raise ValueError('Research project is not active')
            from .decisions import require_undecided
            require_undecided(c,candidate_id)
            d=json.loads(c.execute('SELECT document FROM agent_datasets WHERE id=?',(dataset_id,)).fetchone()[0])
            if d!=dataset:raise ValueError('Dataset access changed; refresh before approving')
            trials=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(project_id,))]
            if any(t['status']=='ACTIVE' for t in trials):raise ValueError('Finish or pause development trials first')
            if sum(t['reserved_runs'] for t in trials)+reserved(c,project_id)+2>budget.max_trial_runs:raise ValueError('Simulation budget exhausted')
            d['state']='INSPECTED_VALIDATION'
            c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(d),dataset_id))
            c.execute('INSERT INTO agent_validations VALUES (?,?,?,?)',(id,project_id,candidate_id,json.dumps(document)))
            c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',(project_id,dataset_id,'candidate_validation_approved',json.dumps({'validation_id':id,'candidate_hash':document['candidate_hash'],'criteria':criteria})))
        return document

    def save(self,document):
        revision=document['revision'];document['revision']+=1
        with self.database.connect() as c:
            return c.execute("UPDATE agent_validations SET document=? WHERE id=? AND json_extract(document,'$.revision')=? AND json_extract(document,'$.status')='ACTIVE'",(json.dumps(document,allow_nan=False),document['id'],revision)).rowcount==1

    def tick(self,jobs):
        for document in self.list():
            if document['status']!='ACTIVE':continue
            try:self.advance(document,jobs)
            except Exception:
                document.update(status='FAILED',error='Validation gate failed; inspect saved jobs. Dataset remains inspected. No automatic retry.')
                self.save(document)

    def advance(self,document,jobs):
        if not active(self.database,document['id']):
            document.update(status='FAILED',error='Validation stopped by project state or time budget');self.save(document)
            for cell in document['cells']:
                job=lookup_job(self.database,key(document,cell['index']))
                if job and job['status'] not in {'completed','failed','cancelled'}:jobs.cancel(job['id'])
            return
        check_source(document['candidate']['snapshot']['hypothesis'])
        cell=next((c for c in document['cells'] if c['status']!='COMPLETED'),None)
        if cell is None:
            runs=BacktestRunRepository(self.database)
            comparison=compare(runs.get(document['cells'][0]['run_id']),runs.get(document['cells'][1]['run_id']))
            if not comparison['data_equivalent']:raise ValueError('Validation data differs')
            document.update(status='COMPLETED',comparison=comparison,verdict=verdict(comparison['child']['summary'],document['criteria']))
            self.save(document);return
        job=lookup_job(self.database,key(document,cell['index']))
        if not job:
            if cell.get('job_id'):raise ValueError('Validation job removed')
            job=jobs.enqueue([cell['payload']],key(document,cell['index']))[0]
        cell.update(job_id=job['id'],status=job['status'].upper())
        if job['status']=='completed':
            run=BacktestRunRepository(self.database).get(job['run_id'])
            if run['config'].get('research_validation_id')!=document['id'] or run['config'].get('research_validation_cell')!=cell['index']:raise ValueError('Saved validation provenance differs')
            report=analyze(run)
            if report['strategy_provenance']!=document['candidate']['snapshot']['source']:raise ValueError('Validation source differs')
            cell.update(status='COMPLETED',run_id=job['run_id'])
            if cell['index']==0:document['data_fingerprint']=report['data_fingerprint']
        elif job['status'] in {'failed','cancelled'}:document.update(status='FAILED',error='Validation job failed/cancelled; no automatic retry; dataset remains inspected')
        self.save(document)


def active(database,id):
    document=Validations(database).get(id)
    return document['status']=='ACTIVE' and now()<document['deadline'] and ResearchRepository(database).get(document['project_id'])['state']=='BASELINE_ANALYSIS'


def validate(database,payload,identity=None):
    document=Validations(database).get(payload['research_validation_id']);index=payload.get('research_validation_cell')
    if not active(database,document['id']) or type(index) is not int or index not in (0,1):raise ValueError('Validation is not active')
    if {k:v for k,v in payload.items() if k!='queue_job_id'}!=document['cells'][index]['payload']:raise ValueError('Payload differs from frozen validation grant')
    job=lookup_job(database,key(document,index))
    if not job or job['id']!=payload.get('queue_job_id'):raise ValueError('Job is not the approved validation')
    if index and document['cells'][0]['status']!='COMPLETED':raise ValueError('Validation baseline must complete first')
    check_source(document['candidate']['snapshot']['hypothesis'])
    if identity is not None and index and identity!=document['data_fingerprint']:raise ValueError('Validation data fingerprint changed')
    return document
