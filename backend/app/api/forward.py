"""Explicit shadow controls. No order-placement or paper-arming routes here."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.api.dependencies import get_services
from app.forward.deployments import ShadowAccount

router=APIRouter(prefix='/forward',tags=['forward-validation'])

class Prepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_key:str=Field(min_length=1,max_length=150)
    account:ShadowAccount
    acknowledgement:Literal['Start four independent IEX shadows; no broker orders']

def service(services=Depends(get_services)):
    instance=getattr(services,'forward',None)
    if instance is None:raise HTTPException(503,'Forward service unavailable')
    return instance

@router.get('')
def report(instance=Depends(service)):
    return instance.report()

@router.post('/prepare')
def prepare(request:Prepare,instance=Depends(service)):
    try:return instance.prepare(request.request_key,request.account.model_dump())
    except ValueError as exc:raise HTTPException(400,str(exc)) from None

@router.post('/{experiment}/halt')
def halt(experiment:str,instance=Depends(service)):
    return instance.halt(experiment)
