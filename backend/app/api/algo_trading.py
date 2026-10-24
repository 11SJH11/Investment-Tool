from fastapi import APIRouter,Depends,Query
from app.api.dependencies import get_services
from app.services.algo_monitoring import report,recovery_page
from app.services.algo_decisions import decision_page

router=APIRouter(prefix='/algo-trading',tags=['algo-monitoring'])


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
