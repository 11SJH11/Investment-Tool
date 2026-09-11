from fastapi import APIRouter, Depends

from app.api.dependencies import get_services
from app.services.container import AppServices


router = APIRouter(tags=["system"])


@router.get("/health")
def health(services: AppServices = Depends(get_services)):
    services.database.initialize()
    return {
        "status": "ok",
        "environment": services.settings.environment,
        "database": "ok",
    }
