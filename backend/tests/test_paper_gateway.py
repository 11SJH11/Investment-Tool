from datetime import datetime,timezone,timedelta
from copy import deepcopy
import sqlite3
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
    def cancel(self,identifier):
        for order in self.orders.values():
            if order['id']==identifier:order['status']='canceled'

@pytest.fixture
def setup(repository):
    experiment=repository.prepare('paper',ACCOUNT,registry=Registry())[0]['experiment_id']
    broker=Broker();gateway=PaperGateway(repository.database,broker,clock=lambda:NOW)
    deployment=gateway.create(experiment,{'fixed_notional':1000})
    gateway.arm(deployment['id'])
    return gateway,broker,deployment['id']

def enter(gateway,identifier,**kwargs):
    return gateway.submit(identifier,decision_at=NOW,action='entry',direction='long',price=500,stop_loss=50,**kwargs)

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
    with pytest.raises(ValueError,match='superseded'):gateway.arm(identifier)

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

def test_explicit_cancel_disarms_and_preserves_partial_position(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],1,'partially_filled');broker.quantity='1'
    cancelled=gateway.cancel_open(identifier)
    assert cancelled['position_qty']=='1' and not cancelled['armed']
    assert gateway.intents(identifier)[0]['state']=='CANCELED'
    assert len(broker.posts)==1

def test_loss_limit_does_not_prevent_explicit_risk_reducing_flatten(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],2);broker.quantity='2'
    broker.positions=lambda:[dict(symbol='QQQ',qty=broker.quantity,avg_entry_price='500')] if float(broker.quantity) else []
    gateway.reconcile(identifier);broker.equity='9000'
    with pytest.raises(ValueError,match='loss'):gateway.reconcile(identifier)
    exit_order=gateway.flatten(identifier)
    assert exit_order['order']['qty']=='2' and exit_order['order']['side']=='sell'
    assert not gateway.get(identifier)['armed']
    assert gateway.get(identifier)['position_qty']=='2'
    broker.fill(exit_order['client_order_id'],2);broker.quantity='0'
    assert gateway.reconcile(identifier,allow_risk_breach=True)['position_qty']=='0'
    assert gateway.flatten(identifier) is None

def test_three_entry_attempts_include_rejected_orders(setup):
    gateway,broker,identifier=setup
    for minute in range(3):
        now=NOW+timedelta(minutes=minute)
        gateway.clock=lambda:now;broker.clock=lambda:dict(is_open=True,timestamp=now.isoformat())
        entry=gateway.submit(identifier,decision_at=now,action='entry',direction='long',price=500,stop_loss=50)
        broker.fill(entry['client_order_id'],0,'rejected')
    now=NOW+timedelta(minutes=3)
    with pytest.raises(ValueError,match='Three'):
        gateway.submit(identifier,decision_at=now,action='entry',direction='long',price=500,stop_loss=50)
    assert len(broker.posts)==3

def test_database_failure_before_durable_intent_never_contacts_broker(setup):
    gateway,broker,identifier=setup
    with gateway.database.connect() as c:
        c.execute("CREATE TRIGGER reject_intent BEFORE INSERT ON forward_paper_intents BEGIN SELECT RAISE(ABORT,'disk fixture'); END")
    with pytest.raises(sqlite3.IntegrityError):enter(gateway,identifier)
    assert not broker.posts and not gateway.intents(identifier)

def test_database_failure_after_post_preserves_unknown_intent_without_retry(setup):
    gateway,broker,identifier=setup
    with gateway.database.connect() as c:
        c.execute("""CREATE TRIGGER reject_ack BEFORE UPDATE ON forward_paper_intents
                     WHEN json_extract(NEW.document,'$.state')='SUBMITTED'
                     BEGIN SELECT RAISE(ABORT,'disk fixture'); END""")
    with pytest.raises(sqlite3.IntegrityError):enter(gateway,identifier)
    assert len(broker.posts)==1 and gateway.intents(identifier)[0]['state']=='SUBMITTING'
    assert not gateway.get(identifier)['armed']
    gateway.reconcile(identifier)
    assert gateway.intents(identifier)[0]['state']=='ACCEPTED'
    enter(gateway,identifier)
    assert len(broker.posts)==1

def protected_position(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],2);broker.quantity='2'
    broker.positions=lambda:[dict(symbol='QQQ',qty=broker.quantity,avg_entry_price='500')] if float(broker.quantity) else []
    broker.clock=lambda:dict(is_open=True,timestamp=gateway.clock().isoformat(),next_close='2026-01-02T21:00:00Z')
    gateway.reconcile(identifier)
    return gateway,broker,identifier

def test_native_closing_auction_is_confirmed_by_lookup_and_never_duplicated(setup):
    gateway,broker,identifier=protected_position(setup)
    protection=gateway.protect_close(identifier)
    assert protection['state']=='SUBMITTED'
    assert protection['order']['time_in_force']=='cls' and protection['order']['side']=='sell'
    confirmed=gateway.protect_close(identifier)
    assert confirmed['state']=='ACCEPTED' and len(broker.posts)==2
    assert gateway.get(identifier)['position_qty']=='2'
    with pytest.raises(ValueError,match='unresolved'):gateway.flatten(identifier)
    gateway.cancel_open(identifier)
    exit_order=gateway.flatten(identifier)
    assert exit_order['order']['time_in_force']=='day' and len(broker.posts)==3

def test_closing_auction_timeout_never_blindly_retries(setup):
    gateway,broker,identifier=protected_position(setup);broker.fail=True
    with pytest.raises(TimeoutError):gateway.protect_close(identifier)
    assert not gateway.get(identifier)['armed']
    assert gateway.protect_close(identifier)['state']=='ACCEPTED'
    assert len(broker.posts)==2

def test_closing_auction_cutoff_rejects_next_session_risk(setup):
    gateway,broker,identifier=protected_position(setup)
    gateway.clock=lambda:datetime(2026,1,2,20,50,tzinfo=timezone.utc)
    with pytest.raises(ValueError,match='cutoff'):gateway.protect_close(identifier)
    assert len(broker.posts)==1

def test_partial_entry_cannot_claim_full_closing_protection(setup):
    gateway,broker,identifier=setup
    entry=enter(gateway,identifier)
    broker.fill(entry['client_order_id'],1,'partially_filled');broker.quantity='1'
    broker.positions=lambda:[dict(symbol='QQQ',qty='1',avg_entry_price='500')]
    broker.clock=lambda:dict(is_open=True,timestamp=NOW.isoformat(),next_close='2026-01-02T21:00Z')
    with pytest.raises(ValueError,match='unresolved'):gateway.protect_close(identifier)
    assert len(broker.posts)==1
