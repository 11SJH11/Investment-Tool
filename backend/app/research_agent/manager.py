"""Deterministic candidate next-step recommendations. No jobs, model calls or approvals."""
import json
from datetime import datetime, timezone
from .analysis import digest
from .candidates import Candidates
from .repository import ResearchRepository
from .trials import Trials
from .hypotheses import Budget
from .validation import reserved
from .decisions import verified_validation


def choose(evidence):
    if evidence['decision']:return 'COMPLETE','A final research decision is already recorded.',0
    if evidence['active']:return 'WAIT','Finish or explicitly cancel the active/paused checks before proceeding.',0
    validation=evidence['validation']
    if validation and validation['verdict']!='VALIDATION_PASS':
        return 'REVIEW_VALIDATION','Review the failed, incomplete or insufficient validation; do not reuse it as unseen data.',0
    for kind,needed in [('cost',2),('regime',3),('simplification',2)]:
        check=evidence['checks'][kind]
        if check and check['status']!='COMPLETED':return 'REVIEW_CHECK_FAILURE',f'Review the {kind} check; its missing result is not a pass.',0
        if not check:
            if evidence['runs_remaining']<needed:return 'STOP_BUDGET',f'Insufficient remaining simulation budget for a minimum {kind} check.',0
            return {'cost':'PLAN_COST_CHECK','regime':'PLAN_REGIME_CHECK','simplification':'REVIEW_ABLATION_PROPOSALS'}[kind],f'Preregister and explicitly approve a {kind} check. No assumptions or approval are supplied by this recommendation.',needed
    if not validation:
        if evidence['runs_remaining']<2:return 'STOP_BUDGET','Insufficient remaining simulation budget for candidate validation.',0
        return 'REQUEST_VALIDATION_APPROVAL','Review development evidence before explicitly approving a candidate-specific validation dataset.',2
    return 'REVIEW_ACCEPTANCE','Passing validation and completed checks are ready for human review; no automatic acceptance or trading approval.',0


def review(database,project_id,candidate_id):
    candidates=Candidates(database)
    candidate=next((c for c in candidates.list(project_id) if c['id']==candidate_id),None)
    if not candidate or digest(candidate['snapshot'])!=candidate['snapshot_hash']:raise ValueError('Valid frozen candidate required')
    _,cell,_=candidates.assess(project_id,candidate['trial_id'],candidate['cell_index'])
    if cell['comparison']['child']['result_digest']!=candidate['snapshot']['result_digest'] or cell['payload']!=candidate['snapshot']['configuration']:raise ValueError('Frozen candidate evidence changed')
    project=ResearchRepository(database).get(project_id)
    trials=Trials(database).list(project_id)
    with database.connect() as c:
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        decision=c.execute('SELECT document FROM agent_decisions WHERE candidate_id=?',(candidate_id,)).fetchone() if 'agent_decisions' in tables else None
        row=c.execute('SELECT document FROM agent_validations WHERE candidate_id=?',(candidate_id,)).fetchone() if 'agent_validations' in tables else None
        validation=json.loads(row[0]) if row else None
        if validation and validation.get('verdict')=='VALIDATION_PASS':validation=verified_validation(c,candidate)
        from .candidate_checks import evidence as check_evidence
        from .regimes import evidence as regime_evidence
        checks={kind:None for kind in ('cost','regime','simplification')}
        for trial in trials:
            if trial.get('candidate_id')==candidate_id and trial.get('kind') in checks:
                checks[trial['kind']]=(regime_evidence if trial['kind']=='regime' else check_evidence)(c,trial)
        remaining=max(0,Budget.model_validate(project.get('research_budget',{})).max_trial_runs-sum(t['reserved_runs'] for t in trials)-reserved(c,project_id))
        sandbox_active=bool(c.execute("SELECT 1 FROM agent_sandbox_runs WHERE project_id=? AND json_extract(document,'$.status') IN ('QUEUED','RUNNING')",(project_id,)).fetchone()) if 'agent_sandbox_runs' in tables else False
    evidence={'candidate_hash':candidate['snapshot_hash'],'checks':checks,'runs_remaining':remaining,
              'active':sandbox_active or any(t['status'] in {'ACTIVE','PAUSED'} for t in trials) or bool(validation and validation['status']=='ACTIVE'),
              'validation':{'status':validation['status'],'verdict':validation.get('verdict'),'id':validation['id']} if validation else None,
              'decision':json.loads(decision[0])['decision'] if decision else None,
              'development_warnings':candidate['snapshot']['robustness']['warnings']}
    action,reason,minimum=choose(evidence)
    report={'version':'candidate_manager_v1','candidate_id':candidate_id,'action':action,'reason':reason,'minimum_new_runs':minimum,
            'evidence':evidence,'evidence_hash':digest(evidence),
            'limitations':['Deterministic workflow guidance, not a profitability ranking or causal conclusion. Missing checks never imply success.',
                          'No model calls, job submission, holdout approval, final decision or live execution. Evidence is a recorded snapshot; refresh after changes.',
                          'Non-passing validation status prompts investigation, not automatic rejection. Passing validation is reverified against saved results.']}
    with database.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        current=json.loads(c.execute('SELECT document FROM agent_projects WHERE id=?',(project_id,)).fetchone()[0])
        if current['state']!='BASELINE_ANALYSIS':raise ValueError('Project is no longer active')
        previous=c.execute("SELECT detail FROM agent_events WHERE project_id=? AND action='candidate_manager_review' ORDER BY rowid DESC LIMIT 1",(project_id,)).fetchone()
        if previous:
            old=json.loads(previous[0])
            if old.get('candidate_id')==candidate_id and old.get('evidence_hash')==report['evidence_hash']:return old
        report['created_at']=datetime.now(timezone.utc).isoformat()
        c.execute('INSERT INTO agent_events(project_id,action,detail) VALUES (?,?,?)',(project_id,'candidate_manager_review',json.dumps(report,allow_nan=False)))
    return report
