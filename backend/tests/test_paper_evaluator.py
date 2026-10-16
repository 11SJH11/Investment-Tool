from datetime import datetime,timezone
import pytest
from app.forward.paper_gateway import PaperGateway
from app.forward.paper_evaluator import PaperEvaluator
from tests.test_forward_deployments import repository
from tests.test_forward_runtime import running,minutes
from tests.test_paper_gateway import Broker

@pytest.fixture
def evaluator(running):
    runtime,experiment,registry=running
    now=[datetime(2026,1,2,14,31,tzinfo=timezone.utc)]
    broker=Broker();gateway=PaperGateway(runtime.database,broker,clock=lambda:now[0])
    item=gateway.create(experiment,{'fixed_notional':1000})
    gateway.reconcile(item['id'])
    return PaperEvaluator(runtime.database,runtime,gateway),item['id'],runtime,experiment,now,broker

def test_paper_decisions_do_not_copy_shadow_positions_or_place_orders(evaluator):
    evaluator,identifier,runtime,experiment,now,broker=evaluator
    runtime.ingest(experiment,minutes(1))
    first=evaluator.evaluate(identifier,now[0])
    assert first['position'] is None and first['result']['kind']=='entry'
    runtime.ingest(experiment,minutes(2));now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc)
    evaluator.gateway.reconcile(identifier)
    assert all(r['state']['position'] for r in runtime.deployments.list(experiment))
    second=evaluator.evaluate(identifier,now[0])
    assert second['position'] is None and second['result']['kind']=='entry'
    assert broker.posts==[]
    restarted=PaperEvaluator(runtime.database,runtime,evaluator.gateway)
    assert restarted.evaluate(identifier,now[0])==second

def test_broker_partial_fill_becomes_paper_context_not_a_simulated_fill(evaluator):
    evaluator,identifier,runtime,experiment,now,broker=evaluator
    runtime.ingest(experiment,minutes(1));evaluator.evaluate(identifier,now[0])
    gateway=evaluator.gateway;gateway.arm(identifier)
    broker.clock=lambda:dict(is_open=True,timestamp=now[0].isoformat())
    intent=gateway.submit(identifier,decision_at=now[0],action='entry',direction='long',price=100,stop_loss=90)
    broker.fill(intent['client_order_id'],1,'partially_filled');broker.quantity='1'
    broker.positions=lambda:[dict(symbol='QQQ',qty='1',avg_entry_price='101')]
    now[0]=datetime(2026,1,2,14,32,tzinfo=timezone.utc)
    gateway.reconcile(identifier);runtime.ingest(experiment,minutes(2))
    result=evaluator.evaluate(identifier,now[0])
    assert result['position']['quantity']==1 and result['position']['entry_price']==101
    assert result['position']['metadata']['entry_time_basis']=='first_fill_observed_at'
    assert result['result'] is None

@pytest.mark.parametrize('fault',['gap','checksum','source','stale'])
def test_paper_recovery_rejects_missing_or_changed_evidence(evaluator,fault):
    evaluator,identifier,runtime,experiment,now,broker=evaluator
    runtime.ingest(experiment,minutes(1));evaluator.evaluate(identifier,now[0])
    now[0]=datetime(2026,1,2,14,34 if fault=='gap' else 14 if fault=='stale' else 32,tzinfo=timezone.utc)
    if fault!='stale':evaluator.gateway.reconcile(identifier)
    if fault=='gap':runtime.ingest(experiment,minutes(4))
    elif fault=='checksum':
        with runtime.database.connect() as c:c.execute("UPDATE forward_paper_decisions SET sha256='invalid'")
        runtime.ingest(experiment,minutes(2))
    elif fault=='source':runtime.registry.content['fixture.py']=b'# changed'
    with pytest.raises(ValueError):evaluator.evaluate(identifier,now[0])
    assert not broker.posts
