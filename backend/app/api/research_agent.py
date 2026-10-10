from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.api.dependencies import get_services
from app.research_agent.repository import ResearchRepository
from app.research_agent.hypotheses import Budget, Hypothesis, HypothesisRepository

router=APIRouter(prefix='/strategy-lab/research-agent',tags=['research-agent'])
class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')
class Dataset(Input):
    start: str
    end: str
    symbols: list[str]=Field(min_length=1,max_length=20)
    timeframe: Literal['1m','5m','15m','30m','1h','4h','1d']
    state: Literal['DEVELOPMENT','INSPECTED','LOCKED_HOLDOUT','FUTURE_OOS']
class Project(Input):
    research_budget: Budget = Field(default_factory=Budget)
    name: str=Field(min_length=1,max_length=120)
    strategy_key: str=Field(min_length=1,max_length=150)
    datasets: list[Dataset]=Field(min_length=1,max_length=20)
class Inspect(Input):
    run_id: int=Field(gt=0)
class Transition(Input):
    state: Literal['PAUSED','BASELINE_ANALYSIS','ARCHIVED']
class Approval(Input):
    acknowledgement: Literal['This dataset will no longer be unseen']

def repo(services=Depends(get_services)):return ResearchRepository(services.database)
def operation(fn):
    try:return fn()
    except ValueError as exc:raise HTTPException(400,str(exc)) from None

@router.get('')
def projects(repository=Depends(repo)):return {'items':repository.list()}
@router.post('')
def create(payload: Project,repository=Depends(repo)):
    return operation(lambda:repository.create(payload.name,payload.strategy_key,[d.model_dump() for d in payload.datasets],payload.research_budget.model_dump()))
@router.get('/{id}')
def project(id: str,services=Depends(get_services)):
    from app.research_agent.workflow import observe
    return operation(lambda:observe(services,id))
@router.post('/{id}/inspect')
def inspect_run(id: str,payload: Inspect,repository=Depends(repo)):return operation(lambda:repository.inspect_run(id,payload.run_id))
@router.post('/{id}/state')
def transition(id: str,payload: Transition,services=Depends(get_services)):
    def update():
        repository=ResearchRepository(services.database);project=repository.get(id)
        if payload.state=='BASELINE_ANALYSIS' and project.get('baseline_job_id') and hasattr(services,'backtest_jobs'):
            try:job=services.backtest_jobs.get(project['baseline_job_id'])
            except ValueError:job={'status':'failed'}
            if job['status'] not in {'failed','cancelled','completed'}:raise ValueError('Wait for the existing baseline job to stop before resuming')
            if job['status']=='completed':
                repository.transition(id,payload.state,completed_baseline=True)
                return repository.inspect_run(id,job['run_id'])
        result=repository.transition(id,payload.state)
        if result['state']=='BASELINE_PENDING' and hasattr(services,'backtest_jobs'):
            from app.research_agent.workflow import start
            return start(services,id,result['baseline_payload'])
        if payload.state in {'PAUSED','ARCHIVED'} and project.get('baseline_job_id') and hasattr(services,'backtest_jobs'):
            try:services.backtest_jobs.cancel(project['baseline_job_id'])
            except ValueError:pass  # Already completed/deleted; saved results remain immutable.
        return result
    return operation(update)
@router.post('/{id}/datasets/{dataset_id}/approve')
def approve(id: str,dataset_id: str,payload: Approval,repository=Depends(repo)):
    return operation(lambda:repository.approve_holdout(id,dataset_id,payload.acknowledgement))


@router.post('/{id}/baseline')
def start_baseline(id: str,payload: dict,services=Depends(get_services)):
    from app.api.strategy_lab import BacktestRequest
    from app.research_agent.workflow import start
    def submit():
        validated=BacktestRequest.model_validate(payload).model_dump()
        return start(services,id,validated)
    return operation(submit)


@router.get('/{id}/hypotheses')
def hypotheses(id: str, services=Depends(get_services)):
    def read():
        ResearchRepository(services.database).get(id)
        return {'items': HypothesisRepository(services.database).list(id)}
    return operation(read)

@router.post('/{id}/hypotheses')
def preregister(id: str, payload: Hypothesis, services=Depends(get_services)):
    return operation(lambda: HypothesisRepository(services.database).register(id, payload.model_dump()))


class CommitteeRequest(Input):
    request_key: str = Field(min_length=1, max_length=120)
    consent: Literal['Send development summaries to the configured model']


def committee_service(services):
    from app.research_agent.committee import Committee
    from app.research_agent.llm import OpenAICommitteeModel
    return Committee(services.database, OpenAICommitteeModel(services.settings))


@router.get('/{id}/committee')
def committee_status(id: str, services=Depends(get_services)):
    return operation(lambda: committee_service(services).public(id))


@router.post('/{id}/committee')
def committee_review(id: str, payload: CommitteeRequest, services=Depends(get_services)):
    return operation(lambda: committee_service(services).review(id, payload.request_key))


@router.post('/{id}/committee/{review_id}/preregister')
def committee_preregister(id: str, review_id: str, services=Depends(get_services)):
    return operation(lambda: committee_service(services).preregister(id, review_id))


class TrialApproval(Input):
    acknowledgement: Literal['Run the frozen control and development variants']


@router.get('/{id}/trials')
def trials(id: str,services=Depends(get_services)):
    from app.research_agent.trials import Trials
    def read():
        project=ResearchRepository(services.database).get(id)
        rows=Trials(services.database).list(id)
        from app.research_agent.validation import reserved
        with services.database.connect() as c:validation_reserved=reserved(c,id)
        return {'items':rows,'reserved_runs':sum(r['reserved_runs'] for r in rows)+validation_reserved,'validation_reserved_runs':validation_reserved,'budget':Budget.model_validate(project.get('research_budget',{})).model_dump()}
    return operation(read)


@router.post('/{id}/hypotheses/{hypothesis_id}/approve')
def approve_trial(id: str,hypothesis_id: str,payload: TrialApproval,services=Depends(get_services)):
    from app.research_agent.trials import Trials
    return operation(lambda:Trials(services.database).approve(id,hypothesis_id))


@router.post('/{id}/trials/{trial_id}/{action}')
def trial_action(id: str,trial_id: str,action: Literal['pause','resume','cancel'],services=Depends(get_services)):
    from app.research_agent.trials import Trials
    def update():
        repository=Trials(services.database)
        if repository.get(trial_id)['project_id']!=id:raise ValueError('Trial belongs to another project')
        return repository.transition(trial_id,action,services.backtest_jobs)
    return operation(update)


class LoopAuthorization(Input):
    acknowledgement: Literal['Authorize bounded model reviews and development backtests']
    max_cycles: int = Field(default=1, ge=1, le=10, strict=True)


@router.get('/{id}/loop')
def research_loop_status(id: str,services=Depends(get_services)):
    return operation(lambda:services.research_loop.get(id))


@router.post('/{id}/loop')
def research_loop_start(id: str,payload: LoopAuthorization,services=Depends(get_services)):
    return operation(lambda:services.research_loop.start(id,payload.max_cycles))


@router.post('/{id}/loop/pause')
def research_loop_pause(id: str,services=Depends(get_services)):
    return operation(lambda:services.research_loop.pause(id))


@router.post('/{id}/loop/resume')
def research_loop_resume(id: str,services=Depends(get_services)):
    return operation(lambda:services.research_loop.resume(id))


class CandidateSelection(Input):
    trial_id: str = Field(min_length=1,max_length=100)
    cell_index: int = Field(ge=1,strict=True)


class CandidateFreeze(CandidateSelection):
    reason: str = Field(min_length=1,max_length=4000)
    acknowledgement: Literal['Freeze this development candidate without consuming holdout data']


@router.get('/{id}/candidates')
def candidates(id: str,services=Depends(get_services)):
    from app.research_agent.candidates import Candidates
    return operation(lambda:{'items':Candidates(services.database).list(id)})


@router.post('/{id}/candidates/assess')
def candidate_assess(id: str,payload: CandidateSelection,services=Depends(get_services)):
    from app.research_agent.candidates import Candidates
    return operation(lambda:Candidates(services.database).assess(id,payload.trial_id,payload.cell_index)[2])


@router.post('/{id}/candidates')
def candidate_freeze(id: str,payload: CandidateFreeze,services=Depends(get_services)):
    from app.research_agent.candidates import Candidates
    return operation(lambda:Candidates(services.database).freeze(id,payload.trial_id,payload.cell_index,payload.reason))


from app.research_agent.validation import Criteria

class ValidationApproval(Input):
    dataset_id: str = Field(min_length=1,max_length=100)
    criteria: Criteria = Field(default_factory=Criteria)
    acknowledgement: Literal['Run this frozen candidate on the selected dataset; it will no longer be unseen']

@router.get('/{id}/validations')
def candidate_validations(id: str,services=Depends(get_services)):
    from app.research_agent.validation import Validations
    def read():
        ResearchRepository(services.database).get(id)
        return {'items':Validations(services.database).list(id)}
    return operation(read)

@router.post('/{id}/candidates/{candidate_id}/validate')
def approve_candidate_validation(id: str,candidate_id: str,payload: ValidationApproval,services=Depends(get_services)):
    from app.research_agent.validation import Validations
    return operation(lambda:Validations(services.database).approve(id,candidate_id,payload.dataset_id,payload.criteria.model_dump()))


from app.research_agent.decisions import Decision

@router.get('/{id}/decisions')
def candidate_decisions(id: str,services=Depends(get_services)):
    from app.research_agent.decisions import Decisions
    return operation(lambda:{'items':Decisions(services.database).list(id)})

@router.post('/{id}/candidates/{candidate_id}/decision')
def record_candidate_decision(id: str,candidate_id: str,payload: Decision,services=Depends(get_services)):
    from app.research_agent.decisions import Decisions
    return operation(lambda:Decisions(services.database).record(id,candidate_id,payload.model_dump()))


from app.research_agent.costs import CostApproval

@router.post('/{id}/candidates/{candidate_id}/costs')
def candidate_cost_approval(id: str,candidate_id: str,payload: CostApproval,services=Depends(get_services)):
    from app.research_agent.costs import approve
    return operation(lambda:approve(services.database,id,candidate_id,payload.model_dump()))

@router.get('/{id}/candidates/{candidate_id}/costs')
def candidate_cost_report(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.costs import report
    return operation(lambda:report(services.database,id,candidate_id))


from app.research_agent.simplification import SimplificationApproval

@router.post('/{id}/candidates/{candidate_id}/simplification')
def candidate_simplification_approval(id: str,candidate_id: str,payload: SimplificationApproval,services=Depends(get_services)):
    from app.research_agent.simplification import approve
    return operation(lambda:approve(services.database,id,candidate_id,payload.model_dump()))

@router.get('/{id}/candidates/{candidate_id}/simplification')
def candidate_simplification_report(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.simplification import report
    return operation(lambda:report(services.database,id,candidate_id))


from app.research_agent.concept_audits import AuditRequest

@router.get('/{id}/concept-audits')
def concept_audits(id: str,services=Depends(get_services)):
    from app.research_agent.concept_audits import ConceptAudits
    return operation(lambda:{'items':ConceptAudits(services.database).list(id)})

@router.post('/{id}/concept-audits')
def run_concept_audit(id: str,payload: AuditRequest,services=Depends(get_services)):
    from app.research_agent.concept_audits import ConceptAudits
    return operation(lambda:ConceptAudits(services.database).run(id,payload.model_dump(mode='json'),services.backtest))


from app.research_agent.regimes import RegimeApproval

@router.post('/{id}/candidates/{candidate_id}/regimes')
def candidate_regime_approval(id: str,candidate_id: str,payload: RegimeApproval,services=Depends(get_services)):
    from app.research_agent.regimes import approve
    return operation(lambda:approve(services.database,id,candidate_id,payload.model_dump(mode='json')))

@router.get('/{id}/candidates/{candidate_id}/regimes')
def candidate_regime_report(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.regimes import report
    return operation(lambda:report(services.database,id,candidate_id))


@router.get('/{id}/candidates/{candidate_id}/simplification-suggestions')
def candidate_simplification_suggestions(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.simplification import suggestions
    return operation(lambda:suggestions(services.database,id,candidate_id))


@router.post('/{id}/candidates/{candidate_id}/manager-review')
def candidate_manager_review(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.manager import review
    return operation(lambda:review(services.database,id,candidate_id))


from app.research_agent.quarantine import Draft

@router.post('/{id}/candidates/{candidate_id}/code-drafts')
def quarantine_code_draft(id: str,candidate_id: str,payload: Draft,services=Depends(get_services)):
    from app.research_agent.quarantine import store
    return operation(lambda:store(services.database,id,candidate_id,payload.model_dump()))


@router.get('/{id}/candidates/{candidate_id}/code-drafts')
def candidate_code_drafts(id: str,candidate_id: str,services=Depends(get_services)):
    from app.research_agent.quarantine import list_drafts
    return operation(lambda:{'items':list_drafts(services.database,id,candidate_id)})

@router.get('/{id}/candidates/{candidate_id}/code-drafts/{draft_id}/source')
def candidate_code_draft_source(id: str,candidate_id: str,draft_id: str,services=Depends(get_services)):
    from app.research_agent.quarantine import export_draft
    return operation(lambda:export_draft(services.database,id,candidate_id,draft_id))


from app.research_agent.sandbox_runs import Approval as SandboxApproval


@router.get('/{id}/sandbox-runs')
def sandbox_runs(id: str,services=Depends(get_services)):
    return operation(lambda:{'items':services.research_sandbox.list(id)})


@router.post('/{id}/candidates/{candidate_id}/code-drafts/{draft_id}/sandbox')
def approve_sandbox(id: str,candidate_id: str,draft_id: str,payload: SandboxApproval,services=Depends(get_services)):
    return operation(lambda:services.research_sandbox.approve(id,candidate_id,draft_id,payload.model_dump()))


@router.post('/{id}/sandbox-runs/{run_id}/cancel')
def cancel_sandbox(id: str,run_id: str,services=Depends(get_services)):
    return operation(lambda:services.research_sandbox.cancel(id,run_id))
