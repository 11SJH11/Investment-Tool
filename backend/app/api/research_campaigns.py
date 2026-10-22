"""Advanced campaign integration API. The minimal-prompt primary UI is still pending."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from app.api.dependencies import get_services
from app.research_agent.campaigns import Campaigns, CampaignRequest
from app.research_agent.campaign_policy import CampaignPolicy, preset
from app.research_agent.dataset_planner import SessionCoverage
from app.research_agent.hypotheses import Strict
from app.research_agent.launch import Launch


router = APIRouter(prefix='/strategy-lab/research-campaigns', tags=['research-campaigns'])


def operation(fn):
    try:
        return fn()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def repository(services=Depends(get_services)):
    return Campaigns(services.database)


class QueueEntry(Strict):
    family_id: str = Field(min_length=1, max_length=150)
    strategy_key: str = Field(min_length=1, max_length=150)
    reason: str = Field(min_length=1, max_length=4000)


class Prepare(Strict):
    entries: list[QueueEntry] = Field(min_length=1, max_length=30)
    coverages: list[SessionCoverage] = Field(min_length=1, max_length=140)


class Development(Strict):
    configurations: dict[str, dict]
    numeric_cycles: int = Field(default=0, ge=0, le=10, strict=True)
    structural: bool = False
    acknowledgement: Literal['Authorize frozen campaign development runs and configured model summaries']


class PrepareHistory(Strict):
    lookback_days: int = Field(default=1460,ge=1,le=3650,strict=True)
    acknowledgement: Literal['Fetch bounded historical data using my configured provider; no strategy execution']


def director(services):
    instance = getattr(services, 'research_director', None)
    if instance is None:
        raise HTTPException(409, 'Research Director is unavailable')
    return instance


@router.get('/policy')
def policy(repo=Depends(repository)):
    return dict(defaults=repo.defaults(), presets={k:preset(k).model_dump() for k in ['QUICK','STANDARD','DEEP']})


@router.put('/policy')
def update_policy(payload: CampaignPolicy, repo=Depends(repository)):
    return repo.defaults(payload.model_dump())


@router.get('')
def campaigns(repo=Depends(repository)):
    return {'items':repo.list()}


@router.post('/launch')
def launch_campaign(payload: Launch, services=Depends(get_services)):
    from app.research_agent.launch import launch
    director(services)
    return operation(lambda:launch(services,payload.model_dump()))


@router.post('')
def create(payload: CampaignRequest, repo=Depends(repository)):
    return operation(lambda: repo.create(payload.model_dump(exclude_unset=True)))


@router.get('/{identifier}')
def campaign(identifier: str, repo=Depends(repository), services=Depends(get_services)):
    def read():
        result = repo.report(identifier)
        worker = getattr(services, 'research_director', None)
        result['worker'] = dict(available=bool(worker),
                                running=bool(worker and worker.thread and worker.thread.is_alive()),
                                error=worker.last_error if worker else None)
        result['worker'].update(last_cycle_started_at=getattr(worker,'last_cycle_started_at',None),
                                last_cycle_finished_at=getattr(worker,'last_cycle_finished_at',None))
        return result
    return operation(read)


@router.post('/{identifier}/prepare')
def prepare(identifier: str, payload: Prepare, repo=Depends(repository)):
    return operation(lambda: repo.prepare(identifier, [e.model_dump() for e in payload.entries],
                                          [c.model_dump(mode='json') for c in payload.coverages]))


@router.get('/{identifier}/activity')
def activity(identifier: str, before: int | None = Query(default=None, ge=1),
             limit: int = Query(default=50, ge=1, le=100), repo=Depends(repository)):
    return operation(lambda: repo.activity(identifier, before=before, limit=limit))


@router.post('/{identifier}/projects')
def projects(identifier: str, services=Depends(get_services)):
    from app.research_agent.campaign_projects import provision
    return operation(lambda: {'items':provision(services.database, identifier)})


@router.post('/{identifier}/auto-prepare')
def auto_prepare(identifier: str, services=Depends(get_services)):
    from app.research_agent.discovery import prepare
    return operation(lambda: prepare(services, identifier))


@router.post('/{identifier}/prepare-history')
def prepare_history(identifier: str, payload: PrepareHistory, services=Depends(get_services)):
    from app.research_agent.preparation import start
    director(services)
    return operation(lambda: start(services,identifier,payload.lookback_days))


@router.post('/{identifier}/development')
def development(identifier: str, payload: Development, services=Depends(get_services)):
    return operation(lambda: director(services).start_baselines(identifier, payload.configurations, numeric_cycles=payload.numeric_cycles, structural=payload.structural))


@router.post('/{identifier}/{action}')
def control(identifier: str, action: Literal['pause','resume','cancel','stop_after_current'], services=Depends(get_services)):
    return operation(lambda: director(services).control(identifier, action))
