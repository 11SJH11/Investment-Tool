from datetime import datetime,timezone
import pytest
from app.forward.paper_coordinator import PaperCoordinator
from app.forward.deployments import encoded
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running,minutes
from tests.test_paper_evaluator import evaluator

@pytest.fixture
def coordinator(evaluator):
    evaluator,identifier,runtime,experiment,now,broker=evaluator
    runtime.ingest(experiment,minutes(1))
    service=PaperCoordinator(runtime.database,runtime,evaluator.gateway)
    broker.clock=lambda:dict(is_open=True,timestamp=now[0].isoformat())
    # Internal simulation only: production coordinator arming is blocked pending
    # broker-managed protection. Never use this setup through application APIs.
    item=evaluator.gateway.arm(identifier);item['start_after']=now[0].isoformat()
    with runtime.database.connect() as c:evaluator.gateway._save(c,item)
    return service,identifier,runtime,experiment,now,broker

def test_explicit_arm_future_decision_and_duplicate_poll(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    assert service.tick(identifier)['status']=='AWAITING_NEXT_COMPLETED_BAR'
    assert not broker.posts
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
    first=service.tick(identifier)
    assert first['status']=='INTENT_SUBMITTED' and len(broker.posts)==1
    assert service.tick(identifier)==first and len(broker.posts)==1

def test_session_flatten_still_managed_after_disarm(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
    first=service.tick(identifier)
    broker.fill(first['client_order_id'],1,'partially_filled');broker.quantity='1'
    broker.positions=lambda:[dict(symbol='QQQ',qty='1',avg_entry_price='100')]
    service.gateway.disarm(identifier)
    now[0]=datetime(2026,1,2,14,35,tzinfo=timezone.utc)
    close=service.tick(identifier)
    assert close['status']=='SESSION_CLOSE_REQUESTED'
    assert broker.posts[-1]['side']=='sell' and broker.posts[-1]['qty']=='1'
    assert not service.gateway.get(identifier)['armed']

def test_crashed_dispatch_is_not_reissued(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    with runtime.database.connect() as c:
        c.execute('INSERT INTO forward_paper_dispatches VALUES (?,?,?)',(identifier,now[0].isoformat(),encoded({'status':'DISPATCH_RESERVED'})))
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
    with pytest.raises(ValueError,match='Interrupted'):service.tick(identifier)
    assert not broker.posts and not service.gateway.get(identifier)['armed']

def test_stale_feed_disarms_without_submission(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    now[0]=datetime(2026,1,2,14,34,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='stale'):service.tick(identifier)
    assert not broker.posts and not service.gateway.get(identifier)['armed']

def test_application_arming_requires_broker_managed_protection(coordinator):
    service,identifier,_,_,_,broker=coordinator
    service.gateway.disarm(identifier)
    with pytest.raises(ValueError,match='not atomic'):service.arm(identifier)
    assert not broker.posts and not service.gateway.get(identifier)['armed']
