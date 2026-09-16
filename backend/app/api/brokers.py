from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import get_services
from app.brokers.base import BrokerHistoryError

router = APIRouter(tags=['broker connections'])


@router.get('/brokers')
def broker_profiles(services=Depends(get_services)):
    return services.broker_connections.statuses()


@router.post('/brokers/{profile_id}/sync')
def sync(profile_id: str, services=Depends(get_services)):
    try:
        return services.broker_connections.sync(profile_id)
    except BrokerHistoryError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get('/portfolio/broker-accounts')
def accounts(services=Depends(get_services)):
    return {'items': services.broker_connections.portfolio.accounts()}


@router.get('/portfolio/broker-records')
def records(account_key: str, kind: str | None = None, limit: int = Query(100, ge=1, le=500),
            offset: int = Query(0,ge=0), services=Depends(get_services)):
    if kind not in {None,'position','orders','dividends','transactions'}:
        raise HTTPException(400,'Unknown Portfolio record type')
    return services.broker_connections.portfolio.records(account_key,kind,limit,offset)


class BrokerReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(default='', max_length=20000)
    tags: list[str] = Field(default_factory=list,max_length=50)


@router.patch('/portfolio/broker-records/{record_id}/review')
def review(record_id: int, body: BrokerReview, services=Depends(get_services)):
    if not services.broker_connections.portfolio.review(record_id, body.note, body.tags):
        raise HTTPException(404,'Portfolio record not found')
    return {'status':'saved'}
