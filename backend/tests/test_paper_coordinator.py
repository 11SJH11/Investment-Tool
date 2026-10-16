from datetime import datetime,timezone
import pytest
import json
from app.forward.paper_protection import ACK
from app.forward.paper_coordinator import PaperCoordinator
from app.forward.deployments import encoded
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running,minutes
from tests.test_paper_evaluator import evaluator

@pytest.fixture
def coordinator(evaluator):
    evaluator,identifier,runtime,experiment,now,broker=evaluator
    with runtime.database.connect() as c:
        sessions=json.loads(c.execute('SELECT sessions_json FROM forward_feeds WHERE experiment_id=?',(experiment,)).fetchone()[0])
        sessions[-1]['close']='2026-01-02T21:00:00+00:00'
        c.execute('UPDATE forward_feeds SET sessions_json=? WHERE experiment_id=?',(json.dumps(sessions),experiment))
    runtime.ingest(experiment,minutes(1))
    service=PaperCoordinator(runtime.database,runtime,evaluator.gateway)
    broker.clock=lambda:dict(is_open=True,timestamp=now[0].isoformat(),next_close='2026-01-02T21:00:00Z')
    service.arm(identifier,ACK)
    return service,identifier,runtime,experiment,now,broker

def test_explicit_arm_future_decision_and_duplicate_poll(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    assert service.tick(identifier)['status']=='AWAITING_NEXT_COMPLETED_BAR'
    assert not broker.posts
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
    first=service.tick(identifier)
    assert first['status']=='INTENT_SUBMITTED' and len(broker.posts)==1
    assert service.tick(identifier)['status']=='ENTRY_FILL_PENDING' and len(broker.posts)==1

def test_broker_protection_survives_disarm_and_session_close(coordinator):
    service,identifier,runtime,experiment,now,broker=coordinator
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc);runtime.ingest(experiment,minutes(2))
    first=service.tick(identifier)
    broker.fill(first['client_order_id'],1,'partially_filled');broker.quantity='1'
    broker.positions=lambda:[dict(symbol='QQQ',qty='1',avg_entry_price='100')]
    service.gateway.disarm(identifier)
    now[0]=datetime(2026,1,2,14,35,tzinfo=timezone.utc)
    service.tick(identifier)
    assert broker.posts[-1]['side']=='sell' and broker.posts[-1]['qty']=='1'
    assert broker.posts[-1]['time_in_force']=='cls'
    assert not service.gateway.get(identifier)['armed']
    now[0]=datetime(2026,1,2,20,59,tzinfo=timezone.utc)
    service.tick(identifier)
    assert len(broker.posts)==2

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
    with pytest.raises(ValueError,match='acknowledgement'):service.arm(identifier)
    assert not broker.posts and not service.gateway.get(identifier)['armed']
