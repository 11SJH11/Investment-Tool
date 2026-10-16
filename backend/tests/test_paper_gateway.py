from datetime import datetime,timezone,timedelta
from copy import deepcopy
import pytest
from app.forward.paper_gateway import PaperGateway
from tests.test_forward_deployments import repository,Registry,ACCOUNT

NOW=datetime(2026,1,2,15,0,tzinfo=timezone.utc)

class Broker:
    def __init__(self):
        self.orders={};self.posts=[];self.quantity='0';self.fail=False
        self.identity='paper-account';self.equity='10000';self.unknown=[]
    def account(self):return dict(id=self.identity,status='ACTIVE',equity=self.equity)
    def positions(self):return [dict(symbol='QQQ',qty=self.quantity)] if float(self.quantity) else []
    def open_orders(self):return self.unknown
    def find(self,key):return deepcopy(self.orders.get(key))
    def clock(self):return dict(is_open=True,timestamp=NOW.isoformat())
    def asset(self):return dict(tradable=True,shortable=True)
    def authorize(self,order,expiry):return 'mock-approval'
    def submit(self,order,approval):
        self.posts.append(deepcopy(order))
        self.orders[order['client_order_id']]={**order,'id':'broker-id','status':'accepted','filled_qty':'0'}
        if self.fail:raise TimeoutError('unknown outcome')
        return self.orders[order['client_order_id']]
    def fill(self,key,qty,status='filled'):
        self.orders[key].update(filled_qty=str(qty),filled_avg_price='500',status=status)

@pytest.fixture
def setup(repository):
    experiment=repository.prepare('paper',ACCOUNT,registry=Registry())[0]['experiment_id']
    broker=Broker();gateway=PaperGateway(repository.database,broker,clock=lambda:NOW)
    deployment=gateway.create(experiment,{'fixed_notional':1000})
    gateway.arm(deployment['id'])
    return gateway,broker,deployment['id']

def enter(gateway,identifier,**kwargs):
    return gateway.submit(identifier,decision_at=NOW,action='entry',direction='long',price=500,**kwargs)

def test_submission_is_not_fill_and_duplicate_intent_never_resubmits(setup):
    gateway,broker,identifier=setup
    first=enter(gateway,identifier)
    assert first['state']=='SUBMITTED' and first['order']['qty']=='2'
    assert gateway.get(identifier)['position_qty']=='0'
    assert enter(gateway,identifier)==first
    assert len(broker.posts)==1

def test_partial_then_final_fill_and_exit_reconcile_from_broker_facts(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],1,'partially_filled');broker.quantity='1'
    assert gateway.reconcile(identifier)['position_qty']=='1'
    with pytest.raises(ValueError,match='unresolved'):
        gateway.submit(identifier,decision_at=NOW,action='exit',direction='long',price=500)
    broker.fill(entry['client_order_id'],2);broker.quantity='2'
    assert gateway.reconcile(identifier)['position_qty']=='2'
    exit_order=gateway.submit(identifier,decision_at=NOW,action='exit',direction='long',price=500)
    assert exit_order['order']['side']=='sell' and exit_order['order']['qty']=='2'
    broker.fill(exit_order['client_order_id'],2);broker.quantity='0'
    assert gateway.reconcile(identifier)['position_qty']=='0'

def test_unknown_submission_reconciles_without_resubmitting_and_restart_disarms(setup):
    gateway,broker,identifier=setup;broker.fail=True
    with pytest.raises(TimeoutError):enter(gateway,identifier)
    assert not gateway.get(identifier)['armed']
    gateway.reconcile(identifier)
    enter(gateway,identifier)
    assert len(broker.posts)==1
    restarted=PaperGateway(gateway.database,broker,clock=lambda:NOW)
    assert not restarted.get(identifier)['armed'] and not restarted.get(identifier)['reconciled']

@pytest.mark.parametrize('fault',['account','position','unknown_order','daily_loss','missing_order','backwards_fill'])
def test_reconciliation_faults_disarm_without_new_orders(setup,fault):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    if fault=='account':broker.identity='different'
    elif fault=='position':broker.quantity='7'
    elif fault=='unknown_order':broker.unknown=[{'client_order_id':'outside-ledger'}]
    elif fault=='daily_loss':broker.equity='9000'
    elif fault=='missing_order':broker.orders.clear()
    else:
        broker.fill(entry['client_order_id'],1,'partially_filled');broker.quantity='1'
        gateway.reconcile(identifier)
        broker.fill(entry['client_order_id'],0,'accepted');broker.quantity='0'
    with pytest.raises(ValueError):gateway.reconcile(identifier)
    assert not gateway.get(identifier)['armed'] and not gateway.get(identifier)['reconciled']
    assert len(broker.posts)==1

@pytest.mark.parametrize('age',[-1,96])
def test_future_or_stale_decision_cannot_submit(setup,age):
    gateway,broker,identifier=setup
    with pytest.raises(ValueError,match='stale'):
        gateway.submit(identifier,decision_at=NOW-timedelta(seconds=age),action='entry',direction='long',price=500)
    assert not broker.posts and not gateway.intents(identifier)
