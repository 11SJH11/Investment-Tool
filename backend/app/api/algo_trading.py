from fastapi import APIRouter,Depends,Query,Header,HTTPException,Request,Response
from app.api.dependencies import get_services
from app.services.algo_monitoring import report,recovery_page
from app.services.algo_decisions import decision_page
from app.services.mt5_deployments import MT5Deployments,DeploymentDraft

router=APIRouter(prefix='/algo-trading',tags=['algo-monitoring'])


def deployment_access(request:Request,response:Response,authorization:str|None=Header(default=None),services=Depends(get_services)):
    import secrets
    from urllib.parse import urlsplit
    response.headers['Cache-Control']='no-store'
    token=getattr(services.settings,'mt5_algo_control_token','')
    if len(token)<32:raise HTTPException(503,'DEMO deployment operator token is not configured')
    if request.url.scheme!='https' and request.url.hostname not in {'127.0.0.1','localhost','::1'}:
        raise HTTPException(403,'Deployment controls require HTTPS or local loopback')
    origin=request.headers.get('origin')
    if origin:
        parsed=urlsplit(origin)
        same=parsed.scheme==request.url.scheme and parsed.netloc==request.url.netloc
        configured=origin in getattr(services.settings,'cors_origins',[])
        secure=parsed.scheme=='https' or (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'})
        if not secure or not (same or configured):raise HTTPException(403,'Cross-origin deployment control denied')
    supplied=(authorization or '').removeprefix('Bearer ')
    if not authorization or not authorization.startswith('Bearer ') or len(supplied)>4096 or not secrets.compare_digest(supplied.encode(),token.encode()):
        raise HTTPException(401,'Deployment operator authentication required')
    return MT5Deployments(services.database,services.broker_connections)


@router.get('/deployments')
def deployments(repository=Depends(deployment_access)):
    try:return dict(items=repository.list(),execution_enabled=False)
    except ValueError as exc:raise HTTPException(409,str(exc)) from None


@router.post('/deployments/preview')
def preview_deployment(body:DeploymentDraft,repository=Depends(deployment_access)):
    from app.brokers.base import BrokerHistoryError
    try:return repository.preview(body.model_dump())
    except (ValueError,BrokerHistoryError) as exc:raise HTTPException(400,str(exc)) from None


@router.post('/deployments')
def create_deployment(body:DeploymentDraft,repository=Depends(deployment_access)):
    from app.brokers.base import BrokerHistoryError
    try:return repository.create(body.model_dump())
    except (ValueError,BrokerHistoryError) as exc:raise HTTPException(400,str(exc)) from None


@router.get('')
def overview(services=Depends(get_services)):
    return report(services)


@router.get('/diagnostic-decisions')
def decisions(stream_id: str=Query(pattern=r'^[a-f0-9]{64}$'),
              before: int|None=Query(None,gt=0),limit: int=Query(50,ge=1,le=100),services=Depends(get_services)):
    return decision_page(services.database,stream_id=stream_id,before=before,limit=limit)


@router.get('/recovery')
def recovery(policy_id: str|None=Query(None,min_length=1,max_length=128),
             before: int|None=Query(None,gt=0),limit: int=Query(50,ge=1,le=100),services=Depends(get_services)):
    return recovery_page(services.database,policy_id=policy_id,before=before,limit=limit)
