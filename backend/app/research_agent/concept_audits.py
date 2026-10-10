"""Explicit, bounded concept audits over a verified project's development baseline."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from time import perf_counter
from uuid import uuid4
from pydantic import Field
from app.market_concepts import registry
from app.market_concepts.base import ConceptRequest
from app.market_concepts.benchmark import benchmark
from app.backtesting.strategies import strategy_registry
from app.services.research_runner import input_identity
from .hypotheses import Strict
from .repository import ResearchRepository
from .analysis import digest
from .access import scope


class AuditGate(ValueError):
    pass


class AuditRequest(Strict):
    request_key: str = Field(min_length=1,max_length=120)
    concept: ConceptRequest
    horizon_bars: int = Field(default=20,ge=1,le=100,strict=True)
    acknowledgement: str = Field(pattern=r'^Audit this concept on verified development data; follow-up metrics are research only$')


class ConceptAudits:
    def __init__(self,database):
        self.database=database;self.projects=ResearchRepository(database)
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_concept_audits(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,request_key TEXT NOT NULL,document TEXT NOT NULL,UNIQUE(project_id,request_key))')

    def list(self,project_id):
        self.projects.get(project_id)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_concept_audits WHERE project_id=? ORDER BY rowid DESC',(project_id,))]
            for row in rows:
                if row['status']=='RUNNING' and datetime.fromisoformat(row['deadline'])<datetime.now(timezone.utc):
                    row.update(status='INTERRUPTED',error='Audit deadline expired. No automatic retry; reservation remains consumed.')
                    c.execute('UPDATE agent_concept_audits SET document=? WHERE id=?',(json.dumps(row),row['id']))
        return rows

    def run(self,project_id,payload,backtest):
        request=AuditRequest.model_validate(payload).model_dump(mode='json')
        previous=next((r for r in self.list(project_id) if r['request']['request_key']==request['request_key']),None)
        if previous:
            if previous['request']!=request:raise ValueError('Audit request key is immutable')
            return previous
        project=self.projects.get(project_id)
        if project['state']!='BASELINE_ANALYSIS' or not project.get('baseline_run_id'):raise ValueError('An active verified development baseline is required')
        project=self.projects.inspect_run(project_id,project['baseline_run_id'])
        report=project['analyses'][str(project['baseline_run_id'])]
        if not report['data_fingerprint'] or report['strategy_provenance']!=project['strategy_provenance'] or strategy_registry.provenance(project['strategy_key'])!=project['strategy_provenance']:
            raise ValueError('Baseline source/data identity is not verified')
        with self.database.connect() as c:
            config=json.loads(c.execute('SELECT config_json FROM backtest_runs WHERE id=?',(project['baseline_run_id'],)).fetchone()[0])
        if not any(d['state'] in {'DEVELOPMENT','INSPECTED'} and set(config['symbols'])<=set(d['symbols']) and d['start']<=config['start_date'] and config['end_date']<=d['end'] for d in project['datasets']):raise ValueError('Concept audits require development data')
        concept=ConceptRequest.model_validate(request['concept']);provenance=registry.provenance(concept)
        stamp=datetime.now(timezone.utc)
        document={'id':str(uuid4()),'project_id':project_id,'request':request,'status':'RUNNING','created_at':stamp.isoformat(),
            'deadline':(stamp+timedelta(minutes=5)).isoformat(),'baseline_run_id':project['baseline_run_id'],
            'baseline_result_digest':report['result_digest'],'data_fingerprint':report['data_fingerprint'],'concept_provenance':provenance}
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_concept_audits WHERE project_id=?',(project_id,))]
            previous=next((r for r in rows if r['request']['request_key']==request['request_key']),None)
            if previous:
                if previous['request']!=request:raise ValueError('Audit request key is immutable')
                return previous
            if len(rows)>=12:raise ValueError('Project concept audit limit reached (12 attempts)')
            if any(r['status']=='RUNNING' for r in rows):raise ValueError('A concept audit is already running')
            current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if current['state']!='BASELINE_ANALYSIS':raise ValueError('Research project must be active')
            c.execute('INSERT INTO agent_concept_audits VALUES (?,?,?,?)',(document['id'],project_id,request['request_key'],json.dumps(document)))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'concept_audit_approved',json.dumps({'audit_id':document['id'],'request_hash':digest(request)})))
        started=perf_counter()
        try:
            config=deepcopy(config)
            for key in ('research_project_id','research_trial_id','research_validation_id','queue_job_id'):config.pop(key,None)
            config['save_run']=False
            with scope(self.database,project_id):
                inputs=backtest.prepare(config)
            if input_identity(inputs)!=document['data_fingerprint']:raise AuditGate('Prepared development data changed')
            symbol=inputs['symbols'][0]
            frame=inputs['frames_by_symbol'][symbol].get(concept.timeframe)
            if frame is None:raise AuditGate('Requested concept timeframe was not prepared by the baseline')
            if not 1<=len(frame)<=2000:raise AuditGate('Concept audits require 1 to 2000 prepared bars; use a smaller declared development baseline')
            output=benchmark(concept,frame,symbol,request['horizon_bars'])
            if output['provenance']!=provenance or registry.provenance(concept)!=provenance:raise AuditGate('Concept implementation changed during audit')
            # Recheck the global firewall and saved baseline before publishing follow-up evidence.
            current=self.projects.inspect_run(project_id,project['baseline_run_id'])
            if current['analyses'][str(project['baseline_run_id'])]['result_digest']!=document['baseline_result_digest']:raise AuditGate('Saved baseline changed')
            if datetime.now(timezone.utc)>datetime.fromisoformat(document['deadline']):raise AuditGate('Audit deadline expired')
            document.update(status='COMPLETED',report=output,report_hash=digest(output))
        except Exception as exc:
            document.update(status='FAILED',error=str(exc) if isinstance(exc,AuditGate) else 'Concept audit failed a source/data/scope/causality/preparation gate. No detector maturity change or automatic retry.')
        document['elapsed_seconds']=round(perf_counter()-started,6)
        with self.database.connect() as c:
            c.execute("UPDATE agent_concept_audits SET document=? WHERE id=? AND json_extract(document,'$.status')='RUNNING'",(json.dumps(document,allow_nan=False),document['id']))
        return next(r for r in self.list(project_id) if r['id']==document['id'])


def committee_evidence(database, project):
    result={}
    rows=[r for r in ConceptAudits(database).list(project['id']) if r['status']=='COMPLETED']
    for record in rows[:3]:
        report=record['report']
        if digest(report)!=record['report_hash']:raise ValueError('Saved concept audit evidence changed')
        if record['data_fingerprint']!=project['analyses'][str(project['baseline_run_id'])]['data_fingerprint']:
            raise ValueError('Concept audit belongs to different development data')
        result['concept_audit/'+record['id']]={k:report[k] for k in ('provenance','bar_count','observation_count','counts','confirmation_lag_seconds','zone_size_midpoint_bps','followup','limitations')}
        result['concept_audit/'+record['id']]['causality']={'status':report['causality']['status'],'probe_count':len(report['causality']['probes'])}
        result['concept_audit/'+record['id']]['interpretation']='Independent detector diagnostics, research-only future outcomes. Not a strategy edge or evidence that this strategy used the detector. Latest three completed audits, chronological selection.'
    return result
