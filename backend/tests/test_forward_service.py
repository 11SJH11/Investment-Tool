from datetime import datetime,timezone
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.dependencies import get_services
from app.api.forward import router
from app.forward.service import ForwardService
from tests.test_forward_deployments import repository,ACCOUNT
from tests.test_forward_runtime import RuntimeRegistry
from tests.test_forward_bars import bar


class Data:
    def __init__(self):self.calls=[]
    def calendar(self,start,end):
        self.calls.append('calendar')
        return [dict(open='2025-12-31T14:30Z',close='2025-12-31T14:32Z'),
                dict(open='2026-01-02T14:30Z',close='2026-01-02T14:36Z')]
    def bars(self,start,end):
        self.calls.append('bars')
        return [bar('2025-12-31T14:30:00+00:00'),bar('2025-12-31T14:31:00+00:00')]
    def close(self):pass

def test_ui_preparation_runs_backend_and_halt_never_places_orders(repository,monkeypatch):
    registry=RuntimeRegistry()
    monkeypatch.setattr('app.backtesting.strategies.strategy_registry',registry)
    monkeypatch.setattr('app.forward.runtime.WARMUP_SESSIONS',1)
    monkeypatch.setattr('app.forward.service.WARMUP_SESSIONS',1)
    provider=Data()
    service=ForwardService(repository.database,SimpleNamespace(alpaca_configured=False),provider=provider,start_thread=False,
                           clock=lambda:datetime(2026,1,2,14,30,tzinfo=timezone.utc))
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(forward=service)
    try:
        with TestClient(app) as client:
            body={'request_key':'api-test','account':ACCOUNT,'acknowledgement':'Start four independent IEX shadows; no broker orders'}
            first=client.post('/forward/prepare',json=body)
            assert first.status_code==200
            experiment=first.json()['items'][0]['id']
            assert not provider.calls
            service.tick()
            report=client.get('/forward').json()
            assert report['items'][0]['preparation']['status']=='READY'
            assert all(d['state']['status']=='ACTIVE' for d in report['items'][0]['deployments'])
            assert client.post('/forward/prepare',json=body).json()['items'][0]['id']==experiment
            halted=client.post(f'/forward/{experiment}/halt').json()
            assert all(d['state']['status']=='HALTED' for d in halted['items'][0]['deployments'])
            assert client.post('/forward/prepare',json={**body,'acknowledgement':'trade live'}).status_code==422
    finally:service.close()

def test_missing_credentials_leave_existing_app_available(repository):
    service=ForwardService(repository.database,SimpleNamespace(alpaca_configured=False),start_thread=False)
    try:
        assert service.report()['configured'] is False
        service.tick()
        assert service.report()['items']==[]
    finally:service.close()


def test_stopping_queued_preparation_prevents_later_activation(repository,monkeypatch):
    monkeypatch.setattr('app.backtesting.strategies.strategy_registry',RuntimeRegistry())
    provider=Data()
    service=ForwardService(repository.database,SimpleNamespace(alpaca_configured=False),provider=provider,start_thread=False)
    try:
        experiment=service.prepare('cancel-queued',ACCOUNT)['items'][0]['id']
        service.halt(experiment)
        service.tick()
        report=service.report(experiment)['items'][0]
        assert report['preparation']['status']=='STOPPED'
        assert not provider.calls
        assert all(d['state']['status']!='ACTIVE' for d in report['deployments'])
    finally:service.close()
