"""Additive research registry. Holdout access is checked before result JSON is read."""
from datetime import date
import json
from uuid import uuid4
from app.data.instruments import normalize_symbol
from app.storage.backtest_run_repository import BacktestRunRepository
from .analysis import analyze, compare, digest

class ResearchRepository:
    def __init__(self,database):
        self.database=database
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_projects(id TEXT PRIMARY KEY, document TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS agent_datasets(id TEXT PRIMARY KEY, document TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS agent_events(id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, dataset_id TEXT, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    def list(self):
        with self.database.connect() as c:
            return [json.loads(row[0]) for row in c.execute('SELECT document FROM agent_projects ORDER BY rowid DESC')]
    def get(self,id):
        with self.database.connect() as c:
            row=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Unknown research project')
            project=json.loads(row[0])
            project['datasets']=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets') if json.loads(r[0])['project_id']==id]
            project['events']=[dict(r) for r in c.execute('SELECT * FROM agent_events WHERE project_id=? ORDER BY id',(id,))]
            project['research_debt']={'uses':sum(e['action']=='inspect_run' for e in project['events']),'hypotheses':sum(e['action']=='hypothesis_preregistered' for e in project['events']),'registered_variants':sum(json.loads(e['detail'])['variants'] for e in project['events'] if e['action']=='hypothesis_preregistered'),'label':'Observed uses only; no mathematically calibrated overfit score.'}
            return project
    def create(self,name,strategy_key,datasets,research_budget=None):
        from .hypotheses import Budget
        budget=Budget.model_validate(research_budget or {}).model_dump()
        from app.backtesting.strategies import strategy_registry
        spec=next((s for s in strategy_registry.specs() if s.key==strategy_key),None)
        if not spec:raise ValueError('Unknown strategy')
        if not name.strip() or not datasets:raise ValueError('Name and datasets are required')
        id=str(uuid4());records=[]
        for d in datasets:
            start=date.fromisoformat(d['start']);end=date.fromisoformat(d['end'])
            if start>end or d['state'] not in {'DEVELOPMENT','INSPECTED','LOCKED_HOLDOUT','FUTURE_OOS'}:raise ValueError('Invalid dataset period/state')
            symbols=sorted({normalize_symbol(s) for s in d['symbols']})
            if not symbols or any(not s for s in symbols):raise ValueError('Dataset symbols are required')
            records.append({'id':str(uuid4()),'project_id':id,'start':str(start),'end':str(end),'symbols':symbols,'state':d['state'],'timeframe':d['timeframe']})
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            existing=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
            for d in records:
                if any(self.overlap(d,e) and (d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} or e['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'}) for e in existing):
                    raise ValueError('Dataset overlaps protected or already registered history; cannot relabel it unseen')
                if d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'}:
                    for row in c.execute('SELECT symbols,start_date,end_date FROM backtest_runs'):
                        if self.overlap(d,{'symbols':json.loads(row['symbols']),'start':row['start_date'],'end':row['end_date']}):
                            raise ValueError('A saved backtest already covers this period; it cannot be declared unseen')
                existing.append(d)
            project={'id':id,'name':name,'strategy_key':strategy_key,'state':'CREATED','mode':'READ_ONLY','research_budget':budget,
                'strategy_provenance':strategy_registry.provenance(strategy_key),'baseline_run_id':None,'analyses':{},'lineage':[]}
            c.execute('INSERT INTO agent_projects VALUES (?,?)',(id,json.dumps(project)))
            c.executemany('INSERT INTO agent_datasets VALUES (?,?)',[(d['id'],json.dumps(d)) for d in records])
        return self.get(id)
    @staticmethod
    def overlap(a,b):
        from .access import family
        return bool({family(s) for s in a['symbols']}&{family(s) for s in b['symbols']}) and a['start']<=b['end'] and b['start']<=a['end']
    def approve_holdout(self,id,dataset_id,acknowledgement):
        if acknowledgement!='This dataset will no longer be unseen':raise ValueError('Explicit irreversible-use acknowledgement required')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT document FROM agent_datasets WHERE id=?',(dataset_id,)).fetchone()
            if not row:raise ValueError('Unknown dataset')
            d=json.loads(row[0])
            project=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()
            if not project or json.loads(project[0])['state']=='ARCHIVED':raise ValueError('Archived or missing project')
            if d['project_id']!=id or d['state'] not in {'LOCKED_HOLDOUT','FUTURE_OOS'}:raise ValueError('Dataset is not a locked holdout for this project')
            # Conservative: consume at approval, before any possible result exposure.
            d['state']='INSPECTED_VALIDATION';c.execute('UPDATE agent_datasets SET document=? WHERE id=?',(json.dumps(d),dataset_id))
            c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',(id,dataset_id,'holdout_approved',acknowledgement))
        return self.get(id)
    def inspect_run(self,id,run_id):
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Unknown project')
            project=json.loads(row[0])
            if project['state'] in {'ARCHIVED','PAUSED'}:raise ValueError('Resume the project before inspecting results')
            # Read only scope metadata before enforcing the global holdout firewall.
            run=c.execute('SELECT symbols,start_date,end_date,strategy_key,primary_timeframe FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
            if not run:raise ValueError('Unknown saved run')
            scope={'symbols':json.loads(run['symbols']),'start':run['start_date'],'end':run['end_date']}
            datasets=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_datasets')]
            if any(self.overlap(scope,d) and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS'} for d in datasets):raise ValueError('Holdout firewall: explicit user approval is required')
            covered=[d for d in datasets if d['project_id']==id and d['timeframe']==run['primary_timeframe'] and set(scope['symbols'])<=set(d['symbols']) and d['start']<=scope['start'] and scope['end']<=d['end']]
            if not covered:raise ValueError('Run falls outside the project dataset registry')
            if run['strategy_key']!=project['strategy_key']:raise ValueError('Register child lineage before using another strategy')
            result_row=c.execute('SELECT config_json,result_json FROM backtest_runs WHERE id=?',(run_id,)).fetchone()
            saved={'config':json.loads(result_row[0]),'result':json.loads(result_row[1])}
            if project['state'] in {'BASELINE_PENDING','BASELINE_RUNNING'} and (not project.get('baseline_job_id') or saved['config'].get('queue_job_id')!=project['baseline_job_id']):
                raise ValueError('Wait for the frozen baseline job before inspecting another run')
            report=analyze(saved);project['analyses'][str(run_id)]=report
            if project['baseline_run_id'] is None:
                if not any(d['state'] in {'DEVELOPMENT','INSPECTED'} for d in covered):raise ValueError('Baseline must use development data')
                project['baseline_run_id']=run_id
                project['lineage'].append({'run_id':run_id,'role':'baseline','source':report['strategy_provenance'],'config_hash':digest(saved['config'])})
            else:
                baseline=c.execute('SELECT config_json,result_json FROM backtest_runs WHERE id=?',(project['baseline_run_id'],)).fetchone()
                if not baseline:raise ValueError('Frozen baseline was deleted')
                project['comparison']=compare({'config':json.loads(baseline[0]),'result':json.loads(baseline[1])},saved)
            project['state']='BASELINE_ANALYSIS';c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(project,allow_nan=False),id))
            for d in covered:
                c.execute('INSERT INTO agent_events(project_id,dataset_id,action,detail) VALUES (?,?,?,?)',(id,d['id'],'inspect_run',json.dumps({'run_id':run_id})))
        return self.get(id)
    def transition(self,id,state,*,completed_baseline=False):
        if state not in {'PAUSED','BASELINE_ANALYSIS','ARCHIVED'}:raise ValueError('Unsupported research transition')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT document FROM agent_projects WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Unknown project')
            project=json.loads(row[0])
            if project['state']=='ARCHIVED':raise ValueError('Archived research cannot resume')
            if state=='BASELINE_ANALYSIS' and project['state']!='PAUSED':raise ValueError('Only paused research can resume')
            if state=='BASELINE_ANALYSIS' and not project.get('baseline_payload') and not project.get('baseline_run_id'):
                state='CREATED'
            if state=='BASELINE_ANALYSIS' and project.get('baseline_payload') and not project.get('baseline_run_id') and not completed_baseline:
                old_job=project.get('baseline_job_id') or project.get('baseline_request_key')
                project['baseline_request_key']='agent-resume:'+str(old_job)
                project['baseline_job_id']=None
                state='BASELINE_PENDING'
            project['state']=state;c.execute('UPDATE agent_projects SET document=? WHERE id=?',(json.dumps(project),id))
        return self.get(id)
