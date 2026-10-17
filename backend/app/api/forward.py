"""Explicit shadow and paper-deployment controls; no arbitrary order endpoint."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.api.dependencies import get_services
from app.forward.deployments import ShadowAccount
from app.forward.paper_gateway import PaperRisk
from app.forward.paper_protection import ACK

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

class ParityRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    session_date:str=Field(pattern=r'^\d{4}-\d{2}-\d{2}$')

@router.post('/{experiment}/parity')
def session_parity(experiment:str,request:ParityRequest,instance=Depends(service)):
    try:return instance.parity.run(experiment,request.session_date)
    except ValueError as exc:raise HTTPException(400,str(exc)) from None
    except Exception:raise HTTPException(502,'Session replay failed; no live execution state was changed') from None

class PaperPrepare(BaseModel):
    model_config=ConfigDict(extra='forbid')
    experiment_id:str
    risk:PaperRisk

class PaperControl(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:Literal['arm','disarm','cancel','flatten']
    acknowledgement:str|None=None

@router.get('/paper')
def paper_report(instance=Depends(service)):
    return instance.paper.report()

@router.post('/paper/prepare')
def paper_prepare(request:PaperPrepare,instance=Depends(service)):
    try:
        instance.paper.create(request.experiment_id,request.risk.model_dump())
        return instance.paper.report()
    except ValueError as exc:raise HTTPException(400,str(exc)) from None

@router.post('/paper/disarm-all')
def paper_disarm_all(instance=Depends(service)):
    instance.paper.disarm_all()
    return instance.paper.report()

@router.post('/paper/{identifier}/control')
def paper_control(identifier:str,request:PaperControl,instance=Depends(service)):
    if request.action=='arm' and request.acknowledgement!=ACK:
        raise HTTPException(400,'Explicit acknowledgement of paper protection gaps is required')
    if request.action in {'cancel','flatten'} and request.acknowledgement!=request.action:
        raise HTTPException(400,'Explicit acknowledgement of '+request.action+' is required')
    try:
        instance.paper.control(identifier,request.action,request.acknowledgement)
        return instance.paper.report()
    except ValueError as exc:raise HTTPException(400,str(exc)) from None
    except Exception:raise HTTPException(502,'Paper operation failed; inspect reconciliation status before retrying') from None
