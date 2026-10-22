from fastapi import APIRouter,Depends,Query
from app.api.dependencies import get_services
from app.services.algo_monitoring import report,recovery_page

router=APIRouter(prefix='/algo-trading',tags=['algo-monitoring'])


@router.get('')
def overview(services=Depends(get_services)):
    return report(services)


@router.get('/recovery')
def recovery(policy_id: str|None=Query(None,min_length=1,max_length=128),
             before: int|None=Query(None,gt=0),limit: int=Query(50,ge=1,le=100),services=Depends(get_services)):
    return recovery_page(services.database,policy_id=policy_id,before=before,limit=limit)
