from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.forward import router
from app.api.dependencies import get_services
from app.forward.paper_service import PaperService
from app.forward.paper_protection import ACK
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running,minutes
from tests.test_paper_evaluator import evaluator
from tests.test_paper_coordinator import coordinator

def test_explicit_api_arm_backend_execution_protection_and_safe_report(coordinator):
    _,identifier,runtime,experiment,now,broker=coordinator
    broker.close=lambda:None
    service=PaperService(runtime.database,SimpleNamespace(alpaca_configured=False),runtime,client=broker,start_thread=False,clock=lambda:now[0])
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(forward=SimpleNamespace(paper=service))
    try:
        with TestClient(app) as api:
            report=api.get('/forward/paper')
            assert report.status_code==200 and 'paper-account' not in report.text
            assert not report.json()['items'][0]['armed']
            assert api.post(f'/forward/paper/{identifier}/control',json={'action':'arm'}).status_code==400
            assert not broker.posts
            armed=api.post(f'/forward/paper/{identifier}/control',json={'action':'arm','acknowledgement':ACK})
            assert armed.status_code==200 and armed.json()['items'][0]['armed']
            now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
            service.tick();assert len(broker.posts)==1
            entry=broker.posts[0];broker.fill(entry['client_order_id'],entry['qty']);broker.quantity=entry['qty']
            broker.positions=lambda:[dict(symbol='QQQ',qty=broker.quantity,avg_entry_price='100')]
            now[0]+=timedelta(seconds=5);service.tick()
            assert len(broker.posts)==2 and broker.posts[-1]['time_in_force']=='cls'
            assert api.get('/forward/paper').json()['items'][0]['close_protection']['protected']
            assert api.post(f'/forward/paper/{identifier}/control',json={'action':'flatten'}).status_code==400
            assert api.post('/forward/paper/disarm-all').status_code==200
            assert not service.gateway.get(identifier)['armed'] and len(broker.posts)==2
    finally:service.close()

def test_unconfigured_paper_service_never_arms(running):
    runtime,_,_=running
    service=PaperService(runtime.database,SimpleNamespace(alpaca_configured=False),runtime,start_thread=False)
    try:
        assert not service.report()['configured']
        service.tick()
        assert not service.report()['items']
    finally:service.close()
