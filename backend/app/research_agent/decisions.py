"""Explicit research acceptance/rejection; never deployment or order authorization."""
from datetime import datetime, timezone
import json
from typing import Literal
from pydantic import Field
from .hypotheses import Strict
from .analysis import compare, digest
from .validation import verdict
from .candidates import Candidates
from .repository import ResearchRepository


class Review(Strict):
    periods: str = Field(min_length=1,max_length=2000)
    winner_retention: str = Field(min_length=1,max_length=2000)
    parameter_sensitivity: str = Field(min_length=1,max_length=2000)
    costs_and_regimes: str = Field(min_length=1,max_length=2000)
    complexity_and_limitations: str = Field(min_length=1,max_length=2000)


class Decision(Strict):
    decision: Literal['ACCEPTED_FOR_RESEARCH','REJECTED']
    reason: str = Field(min_length=1,max_length=4000)
    review: Review | None = None
    acknowledgement: Literal['Record this research decision; it does not authorize live trading']


def verified_validation(connection,candidate):
    row=connection.execute('SELECT document FROM agent_validations WHERE candidate_id=?',(candidate['id'],)).fetchone()
    if not row:raise ValueError('A completed passing validation is required')
    validation=json.loads(row[0])
    if validation['status']!='COMPLETED' or validation['verdict']!='VALIDATION_PASS':raise ValueError('A completed passing validation is required')
    if validation['candidate_hash']!=candidate['snapshot_hash']:raise ValueError('Validation belongs to different candidate evidence')
    approvals=[dict(r) for r in connection.execute("SELECT dataset_id,detail FROM agent_events WHERE project_id=? AND action='candidate_validation_approved'",(candidate['project_id'],))]
    approved=next((r for r in approvals if json.loads(r['detail']).get('validation_id')==validation['id']),None)
    if not approved or json.loads(approved['detail']).get('criteria')!=validation['criteria'] or json.loads(approved['detail']).get('candidate_hash')!=candidate['snapshot_hash']:
        raise ValueError('Approved validation criteria or candidate identity changed')
    row=connection.execute('SELECT document FROM agent_datasets WHERE id=?',(approved['dataset_id'],)).fetchone()
    dataset=json.loads(row[0]) if row else None
    if not dataset or dataset['project_id']!=candidate['project_id'] or dataset['state']!='INSPECTED_VALIDATION':raise ValueError('Approved validation dataset is not available')
    runs=[]
    for cell in validation['cells']:
        row=connection.execute('SELECT config_json,result_json FROM backtest_runs WHERE id=?',(cell.get('run_id'),)).fetchone()
        if not row:raise ValueError('Validation result was deleted')
        config=json.loads(row[0])
        if config.get('research_validation_id')!=validation['id'] or config.get('research_validation_cell')!=cell['index'] or config.get('strategy_params',{})!=cell['payload'].get('strategy_params',{}):
            raise ValueError('Validation run identity changed')
        if config.get('start_date')!=dataset['start'] or config.get('end_date')!=dataset['end'] or set(config.get('symbols',[]))!=set(dataset['symbols']) or config.get('primary_timeframe')!=dataset['timeframe']:
            raise ValueError('Validation dataset scope changed')
        runs.append({'config':config,'result':json.loads(row[1])})
    result=compare(*runs)
    if not result['data_equivalent'] or result['parent']['data_fingerprint']!=validation['data_fingerprint'] or digest(result)!=digest(validation['comparison']):raise ValueError('Validation evidence changed')
    if any(result[k]['strategy_provenance']!=candidate['snapshot']['source'] for k in ('parent','child')):raise ValueError('Validation source identity differs')
    if verdict(result['child']['summary'],validation['criteria'])!='VALIDATION_PASS':raise ValueError('Validation criteria no longer pass')
    return validation


class Decisions:
    def __init__(self,database):
        self.database=database;Candidates(database)
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_decisions(candidate_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,document TEXT NOT NULL)')

    def list(self,project_id):
        ResearchRepository(self.database).get(project_id)
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM agent_decisions WHERE project_id=? ORDER BY rowid',(project_id,))]

    def record(self,project_id,candidate_id,payload):
        payload=Decision.model_validate(payload).model_dump()
        if payload['decision']=='ACCEPTED_FOR_RESEARCH' and not payload['review']:raise ValueError('Complete the structured evidence review before accepting')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT document FROM agent_decisions WHERE candidate_id=?',(candidate_id,)).fetchone()
            if prior:
                old=json.loads(prior[0])
                if old['project_id']!=project_id:raise ValueError('Candidate belongs to another project')
                if old['request']!=payload:raise ValueError('Research decision is immutable; create a new candidate for new evidence')
                return old
            row=c.execute('SELECT document FROM agent_candidates WHERE id=? AND project_id=?',(candidate_id,project_id)).fetchone()
            if not row:raise ValueError('Unknown frozen candidate')
            candidate=json.loads(row[0])
            project=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
            if project['state']!='BASELINE_ANALYSIS':raise ValueError('Research project must be active')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_sandbox_runs'").fetchone() and c.execute("SELECT 1 FROM agent_sandbox_runs WHERE project_id=? AND json_extract(document,'$.status') IN ('QUEUED','RUNNING')",(project_id,)).fetchone():
                raise ValueError('Finish or cancel isolated generated-code trials before recording a decision')
            if digest(candidate['snapshot'])!=candidate['snapshot_hash']:raise ValueError('Frozen candidate snapshot changed')
            validation=None
            has_validations=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_validations'").fetchone()
            if has_validations:
                row=c.execute('SELECT document FROM agent_validations WHERE candidate_id=?',(candidate_id,)).fetchone()
                validation=json.loads(row[0]) if row else None
            if validation and validation['status']=='ACTIVE':raise ValueError('Finish validation or pause the project before recording a decision')
            if payload['decision']=='ACCEPTED_FOR_RESEARCH':
                if not has_validations:raise ValueError('A completed passing validation is required')
                validation=verified_validation(c,candidate)
            cost_trials=[json.loads(r[0]) for r in c.execute('SELECT document FROM agent_trials WHERE project_id=?',(project_id,))]
            regime_trials=[t for t in cost_trials if t.get('kind')=='regime' and t.get('candidate_id')==candidate_id]
            if any(t['status'] in {'ACTIVE','PAUSED'} for t in regime_trials):raise ValueError('Finish or cancel candidate regime trials before recording a decision')
            from .regimes import evidence as regime_evidence
            regimes=[regime_evidence(c,t) for t in regime_trials]
            simplification_trials=[t for t in cost_trials if t.get('kind')=='simplification' and t.get('candidate_id')==candidate_id]
            if any(t['status'] in {'ACTIVE','PAUSED'} for t in simplification_trials):raise ValueError('Finish or cancel candidate simplification trials before recording a decision')
            cost_trials=[t for t in cost_trials if t.get('kind')=='cost' and t.get('candidate_id')==candidate_id]
            if any(t['status'] in {'ACTIVE','PAUSED'} for t in cost_trials):raise ValueError('Finish or cancel candidate cost trials before recording a decision')
            from .candidate_checks import evidence
            cost_evidence=[evidence(c,t) for t in cost_trials]
            simplification_evidence=[evidence(c,t) for t in simplification_trials]
            document={'candidate_id':candidate_id,'project_id':project_id,'created_at':datetime.now(timezone.utc).isoformat(),
                'request':payload,'decision':payload['decision'],'candidate_hash':candidate['snapshot_hash'],
                'validation_id':validation['id'] if validation else None,'validation_hash':digest(validation) if validation else None,
                'simplification_evidence':simplification_evidence,'simplification_evidence_hash':digest(simplification_evidence),
                'regime_evidence':regimes,'regime_evidence_hash':digest(regimes),
                'cost_evidence':cost_evidence,'cost_evidence_hash':digest(cost_evidence),
                'development_warnings':candidate['snapshot']['robustness']['warnings'],
                'scope':'Research decision only; no strategy replacement, deployment, live trading or claim of unperformed robustness tests.'}
            c.execute('INSERT INTO agent_decisions VALUES (?,?,?)',(candidate_id,project_id,json.dumps(document,allow_nan=False)))
            c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'candidate_decision',json.dumps({'candidate_id':candidate_id,'decision':document['decision'],'candidate_hash':document['candidate_hash']})))
        return document


def require_undecided(connection,candidate_id):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_decisions'").fetchone() and connection.execute('SELECT 1 FROM agent_decisions WHERE candidate_id=?',(candidate_id,)).fetchone():
        raise ValueError('Candidate already has a final research decision')
