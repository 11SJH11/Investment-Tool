from fastapi import APIRouter,Depends
from app.api.dependencies import get_services
from app.services.algo_monitoring import report

router=APIRouter(prefix='/algo-trading',tags=['algo-monitoring'])


@router.get('')
def overview(services=Depends(get_services)):
    return report(services)
