from concurrent.futures import ThreadPoolExecutor

import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from app.storage.database import Database


def policy(**changes):
    return dict(account_key='a'*64,environment='demo',strategy_key='fixture',strategy_source_hash='b'*64,
        currency='USD',symbols=['XAUUSDs'],max_trade_risk=100,max_daily_loss=300,max_positions=2,max_gross_exposure=10000,**changes)


def order():
    return dict(request_key='signal-1',symbol='XAUUSDs',side='buy',entry=3000,stop=2990,target=3020,quantity_lots=.1)


@pytest.fixture
def ledger(tmp_path):
    db=Database(tmp_path/'execution.db');db.initialize()
    return MT5ExecutionLedger(db)


def test_default_disabled_immutable_policy_and_idempotent_draft(ledger):
    p=ledger.configure(policy())
    assert p==ledger.configure(policy()) and not p['enabled'] and not p['reconciled']
    first=ledger.draft(p['id'],order())
    assert first==ledger.draft(p['id'],order()) and first['state']=='DRAFT'
    assert first['strategy_source_hash']=='b'*64
    assert len(ledger.policies())==len(ledger.intents(p['id']))==1
    with pytest.raises(ValueError,match='disabled'):ledger.authorize_submission(first['id'])


def test_changed_order_cannot_reuse_request_key(ledger):
    p=ledger.configure(policy());ledger.draft(p['id'],order())
    with pytest.raises(ValueError,match='Idempotency'):
        ledger.draft(p['id'],{**order(),'quantity_lots':.2})


def test_concurrent_drafts_create_one_intent(ledger):
    p=ledger.configure(policy())
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda _:ledger.draft(p['id'],order()),range(8)))
    assert len({r['id'] for r in rows})==len(ledger.intents(p['id']))==1


def test_restart_fences_old_writer_and_preserves_draft(ledger):
    p=ledger.configure(policy());first=ledger.draft(p['id'],order())
    restarted=MT5ExecutionLedger(ledger.database)
    assert restarted.policies()[0]['status']=='RESTART_RECONCILIATION_REQUIRED'
    assert restarted.intents(p['id'])==[first]
    with pytest.raises(ValueError,match='superseded'):ledger.draft(p['id'],order())
    assert restarted.draft(p['id'],order())==first
    with pytest.raises(ValueError,match='disabled'):restarted.authorize_submission(first['id'])


@pytest.mark.parametrize('change',[{'environment':'live'},{'account_key':'c'*64},{'strategy_source_hash':'d'*64},{'strategy_key':'other'}])
def test_account_environment_and_strategy_are_separate(ledger,change):
    a=ledger.configure(policy());b=ledger.configure({**policy(),**change})
    assert a['id']!=b['id']
    assert ledger.draft(a['id'],order())['id']!=ledger.draft(b['id'],order())['id']
    assert not b['enabled']


@pytest.mark.parametrize('change',[{'max_trade_risk':0},{'max_daily_loss':float('nan')},{'enabled':True},{'max_positions':1.5}])
def test_invalid_limits_and_arming_not_accepted(ledger,change):
    with pytest.raises(ValueError):ledger.configure({**policy(),**change})
    assert ledger.policies()==[]


def test_symbol_and_stop_target_permissions(ledger):
    p=ledger.configure(policy())
    for change in [{'symbol':'NASUSD'},{'stop':3001},{'target':2999},{'quantity_lots':0}]:
        with pytest.raises(ValueError):ledger.draft(p['id'],{**order(),**change})
    assert ledger.intents(p['id'])==[]


def test_research_cannot_create_policy_or_draft(ledger):
    from app.research_agent.access import preparation_scope
    p=ledger.configure(policy())
    with preparation_scope(ledger.database,'fixture'):
        with pytest.raises(ValueError,match='Research'):ledger.configure(policy())
        with pytest.raises(ValueError,match='Research'):ledger.draft(p['id'],order())


def test_emergency_stop_does_not_claim_position_closure(ledger):
    p=ledger.configure(policy());draft=ledger.draft(p['id'],order())
    assert ledger.emergency_stop()=={'status':'disabled','positions_closed':False}
    assert ledger.policies()[0]['status']=='EMERGENCY_STOP'
    assert ledger.intents(p['id'])==[draft]
