"""Mocked native submission only. These fixtures do not prove broker acceptance."""
from types import SimpleNamespace as NS
import pytest
from app.brokers.mt5_demo_submission import DemoSubmission
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger
from tests.test_mt5_execution_preflight import context
from tests.test_mt5_order_preparation import prepared
from tests.test_mt5_execution_coordinator import gateway


@pytest.fixture
def submission(gateway,monkeypatch):
    ledger,adapter,policy,intent,_=gateway
    monkeypatch.setattr('app.brokers.mt5_demo_submission.collect',lambda a:dict(account_key=a.account_key,
        environment='demo',currency='USD',complete=True,executions=[],open_positions={},
        pending_order_ids=[],observed_at_ms=101000,completed_at_ms=101000))
    sends=[]
    def send(request):
        # The irreversible call cannot precede its durable uncertainty marker.
        assert ledger.attempt(intent['id'])['state']=='SUBMISSION_UNCERTAIN'
        sends.append(request)
        return NS(retcode=10009,order=54321,comment='private native text')
    adapter._module.order_send=send
    return DemoSubmission(ledger,require_authority=lambda **kw:True),adapter,policy,intent,sends


def run(submission):
    gateway,adapter,policy,intent,_=submission
    return gateway.submit(adapter,policy['id'],intent['id'],risk_percent=1,session_key='fixture-session',magic=12345,deviation_points=10)


def test_default_gate_cannot_submit_even_with_passing_broker_checks(submission):
    gateway,adapter,policy,intent,sends=submission
    with pytest.raises(ValueError,match='authority'):
        DemoSubmission(gateway.ledger).submit(adapter,policy['id'],intent['id'],risk_percent=1,
            session_key='fixture-session',magic=12345,deviation_points=10)
    assert sends==[] and gateway.ledger.attempt(intent['id']) is None


def test_protected_order_has_write_ahead_receipt_and_never_blindly_retries(submission):
    result=run(submission);gateway,_,policy,intent,sends=submission
    assert result['status']=='RECEIPT_RECORDED_RECONCILIATION_REQUIRED'
    assert not result['protection_verified'] and not result['position_verified']
    assert sends[0]['sl']==2991 and sends[0]['tp']==3011 and sends[0]['volume']==.1
    assert len(sends)==1 and 'private native text' not in str(result)
    assert gateway.ledger.attempt(intent['id'])['receipt']=={'retcode':10009,'broker_order_id':'54321'}
    assert gateway.ledger.account_guard_status(policy['id'])['state']=='RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError):run(submission)
    assert len(sends)==1


@pytest.mark.parametrize('kind',['timeout','none','malformed','partial','rejected'])
def test_uncertain_partial_and_rejected_never_clear_account_guard(submission,kind):
    gateway,adapter,policy,intent,sends=submission
    def send(request):
        sends.append(request)
        if kind=='timeout':raise TimeoutError('private credentials')
        if kind=='none':return None
        if kind=='malformed':return NS(retcode='bad',order=0)
        return NS(retcode=10010 if kind=='partial' else 10019,order=123 if kind=='partial' else 0)
    adapter._module.order_send=send
    result=run(submission)
    assert 'private credentials' not in str(result)
    assert gateway.ledger.account_guard_status(policy['id'])['state']=='RECONCILIATION_REQUIRED'
    assert gateway.ledger.attempt(intent['id']) is not None
    with pytest.raises(ValueError):run(submission)
    assert len(sends)==1


@pytest.mark.parametrize('kind',['live','identity','source_revoked','false_authority','missing_history','loss_limit','quote_changed'])
def test_unsafe_entry_never_reaches_native_send(submission,kind):
    gateway,adapter,policy,intent,sends=submission
    if kind=='live':adapter.environment='live'
    if kind=='identity':adapter.account_key='c'*64
    if kind=='false_authority':gateway.require_authority=lambda **kw:False
    if kind=='source_revoked':
        calls=[]
        def authorize(**kw):
            calls.append(1)
            if len(calls)>1:raise ValueError('source changed')
            return True
        gateway.require_authority=authorize
    if kind=='missing_history':adapter._module.history_deals_get=lambda *args:None
    if kind=='loss_limit':
        adapter._module.history_deals_get=lambda *args:[NS(ticket=9,type=0,time_msc=99000,profit=-1000.,commission=0.,swap=0.,fee=0.)]
    if kind=='quote_changed':
        calls=[];old=adapter._module.order_check
        def check(request):
            calls.append(1)
            if len(calls)==2:adapter._module.symbol_info_tick=lambda _:NS(time_msc=100000,bid=3000.,ask=3002.)
            return old(request)
        adapter._module.order_check=check
    try:
        result=run(submission)
        assert result['status']=='RISK_REJECTED'
    except (ValueError,RuntimeError):pass
    assert sends==[] and gateway.ledger.attempt(intent['id']) is None


def test_restart_preserves_uncertainty_and_fences_old_gateway(submission):
    gateway,adapter,policy,intent,sends=submission
    run(submission)
    restarted=MT5ExecutionLedger(gateway.ledger.database)
    assert restarted.attempt(intent['id'])['receipt']['broker_order_id']=='54321'
    assert restarted.account_guard_status(policy['id'])['state']=='RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError):run(submission)
    assert len(sends)==1


@pytest.fixture
def managed(submission,monkeypatch):
    from dataclasses import replace
    from tests.test_mt5_execution_reconciliation import execution
    run(submission)
    gateway,adapter,policy,intent,sends=submission
    position=NS(ticket=777,identifier=200,symbol='XAUUSDs',type=0,volume=.1,sl=2991.,tp=3011.)
    fills=[replace(execution(),order_id='54321',price='3001')]
    def snapshot(a):
        return dict(account_key=a.account_key,environment=a.environment,currency='USD',complete=True,
            executions=fills,open_positions={'200':dict(symbol=position.symbol,side='buy',quantity_lots=position.volume,stop=position.sl,target=position.tp)},
            pending_order_ids=[],observed_at_ms=101000,completed_at_ms=101000)
    monkeypatch.setattr('app.brokers.mt5_demo_submission.collect',snapshot)
    assert gateway.recover(adapter,policy['id'])['account_released']
    adapter._module.positions_get=lambda:[position]
    adapter._module.TRADE_ACTION_SLTP=6
    adapter._module.symbol_info('XAUUSDs').trade_freeze_level=0
    adapter._module.symbol_info_tick=lambda _:NS(bid=3008.,ask=3009.,time_msc=101000)
    def modify(request):
        sends.append(request);position.sl=request['sl']
        return NS(retcode=10009)
    adapter._module.order_send=modify
    return submission,position,fills


def tighten(managed,**changes):
    submission,_,_=managed
    gateway,adapter,policy,intent,_=submission
    return gateway.tighten_stop(adapter,policy['id'],intent['id'],**(dict(decision_id='completed-bar-fixture',new_stop=3001.)|changes))


def test_receipt_owned_breakeven_is_verified_idempotent_and_preserves_target(managed):
    submission,position,_=managed;gateway,adapter,policy,intent,sends=submission
    before=gateway.ledger.intents(policy['id'])
    result=tighten(managed)
    assert result['state']=='VERIFIED' and position.sl==3001. and position.tp==3011.
    assert sends[-1]==dict(action=6,position=777,symbol='XAUUSDs',sl=3001.,tp=3011.)
    assert tighten(managed)==result and len(sends)==2
    assert gateway.ledger.intents(policy['id'])==before
    recovery=gateway.recover(adapter,policy['id'])
    assert recovery['account_released'] and recovery['observations'][0]['decision']['state']=='FILLED_PROTECTED'
    assert recovery['observations'][0]['verified_protection_id']==result['id']


@pytest.mark.parametrize('failure',['loosen','manual_scale_in','live','wrong_target','freeze','unverified_authority'])
def test_unsafe_modification_never_touches_native_position(managed,failure):
    from dataclasses import replace
    submission,position,fills=managed;gateway,adapter,_,_,sends=submission
    changes={}
    if failure=='loosen':changes['new_stop']=2990.
    if failure=='manual_scale_in':fills.append(replace(fills[0],external_id='other',order_id='manual',quantity='.1'))
    if failure=='live':adapter.environment='live'
    if failure=='wrong_target':position.tp=3012.
    if failure=='freeze':adapter._module.symbol_info('XAUUSDs').trade_freeze_level=10000
    if failure=='unverified_authority':gateway.require_authority=lambda **kw:False
    with pytest.raises(ValueError):tighten(managed,**changes)
    assert len(sends)==1 and position.sl==2991.


def test_uncertain_modification_is_retained_without_resend(managed):
    submission,position,_=managed;gateway,adapter,policy,_,sends=submission
    def timeout(request):
        sends.append(request);raise TimeoutError('secret')
    adapter._module.order_send=timeout
    result=tighten(managed)
    assert result['state']=='SUBMISSION_UNCERTAIN' and 'secret' not in str(result)
    assert tighten(managed)==result and len(sends)==2
    assert not gateway.recover(adapter,policy['id'])['account_released']
