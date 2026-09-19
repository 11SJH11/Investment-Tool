from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.api.strategy_lab import BacktestRequest
from app.services.strategy_workspace import StrategyWorkspace, syntax


def local_only(request: Request):
    if not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403, 'Strategy Workspace is available only on the local computer')
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).hostname not in {'localhost','127.0.0.1','::1'}:
        raise HTTPException(403, 'Remote browser origins cannot access Strategy Workspace')


router = APIRouter(prefix='/strategy-workspace', tags=['strategy-workspace'], dependencies=[Depends(local_only)])


def workspace(): return StrategyWorkspace()


class Draft(BaseModel):
    filename: str = Field(max_length=100)
    source: str = Field(max_length=100_000)
    expected_revision: str | None = None
    trusted: bool = False


class Execution(Draft):
    action: str
    backtest: BacktestRequest | None = None


def checked(call):
    try: return call()
    except ValueError as exc: raise HTTPException(400, str(exc)) from None
    except OSError: raise HTTPException(503, 'Workspace file or subprocess operation failed') from None


@router.get('/files')
def files(service=Depends(workspace)):
    return checked(service.list)


@router.get('/files/{filename}')
def read(filename: str, service=Depends(workspace)):
    return checked(lambda: service.read(filename))


@router.put('/files')
def save(draft: Draft, service=Depends(workspace)):
    return checked(lambda: service.save(draft.filename, draft.source, draft.expected_revision))


@router.post('/syntax')
def validate_syntax(draft: Draft):
    return checked(lambda: syntax(draft.source))


@router.post('/execute')
def execute(draft: Execution, service=Depends(workspace), services=Depends(get_services)):
    if draft.action == 'backtest' and draft.backtest is None:
        raise HTTPException(400, 'Backtest settings are required')
    return checked(lambda: service.execute(draft.action, draft.filename, draft.source,
        trusted=draft.trusted, services=services,
        payload=draft.backtest.model_dump() if draft.backtest else None))


@router.post('/activate')
def activate(draft: Draft, service=Depends(workspace), services=Depends(get_services)):
    return checked(lambda: service.activate(draft.filename, draft.source, trusted=draft.trusted, services=services))


@router.post('/deactivate')
def deactivate(draft: Draft, service=Depends(workspace)):
    return checked(lambda: service.deactivate(draft.filename))
