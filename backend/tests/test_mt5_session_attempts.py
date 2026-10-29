"""Durable execution budgets; no native broker calls."""
import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger, policy, order


def reserve(ledger, *, session='2026-10-28:NY-Asia'):
    p=ledger.configure(policy())
    intent=ledger.draft(p['id'],order())
    options={} if session is None else dict(session_key=session,max_session_trades=1)
    with ledger.account_guard(p['id']) as token:
        attempt=ledger.begin_attempt(intent['id'],guard_token=token,**options)
    return p,intent,attempt


def test_unknown_outcome_consumes_only_its_recorded_session_across_restart(ledger):
    p,intent,attempt=reserve(ledger)
    assert attempt['session_key']=='2026-10-28:NY-Asia'
    restarted=MT5ExecutionLedger(ledger.database)
    assert restarted.session_attempt_count(p['id'],'2026-10-28:NY-Asia')==1
    assert restarted.session_attempt_count(p['id'],'2026-10-29:NY-Asia')==0
    assert restarted.attempt(intent['id'])==attempt
    # A new day does not forgive an uncertain broker outcome or arm anything.
    assert restarted.account_guard_status(p['id'])['state']=='RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('change,expected',[
    ({'max_trade_risk':50},1),
    ({'strategy_source_hash':'c'*64},1),
    ({'account_key':'c'*64},0),
    ({'strategy_key':'different'},0),
])
def test_changed_settings_cannot_reset_account_strategy_budget(ledger,change,expected):
    reserve(ledger)
    p=ledger.configure(policy()|change)
    assert ledger.session_attempt_count(p['id'],'2026-10-28:NY-Asia')==expected


def test_legacy_unknown_session_is_never_silently_excluded(ledger):
    p,_,attempt=reserve(ledger,session=None)
    assert 'session_key' not in attempt
    assert ledger.session_attempt_count(p['id'],'2026-10-28:NY-Asia')==1
    assert ledger.session_attempt_count(p['id'],'2026-10-29:NY-Asia')==1


@pytest.mark.parametrize('options',[
    {'session_key':'day'}, {'max_session_trades':1},
    {'session_key':' ', 'max_session_trades':1},
    {'session_key':'day','max_session_trades':True},
    {'session_key':'day','max_session_trades':0},
])
def test_invalid_budget_cannot_write_attempt(ledger,options):
    p=ledger.configure(policy());intent=ledger.draft(p['id'],order())
    with ledger.account_guard(p['id']) as token:
        with pytest.raises(ValueError,match='session'):
            ledger.begin_attempt(intent['id'],guard_token=token,**options)
    assert ledger.attempt(intent['id']) is None


def test_limit_rechecked_in_write_ahead_transaction(ledger,monkeypatch):
    p=ledger.configure(policy());intent=ledger.draft(p['id'],order())
    def count(policy_id,session_key,*,_connection=None):
        assert _connection is not None and _connection.in_transaction
        return 1
    monkeypatch.setattr(ledger,'session_attempt_count',count)
    with ledger.account_guard(p['id']) as token:
        with pytest.raises(ValueError,match='Session trade limit'):
            ledger.begin_attempt(intent['id'],guard_token=token,session_key='day',max_session_trades=1)
    assert ledger.attempt(intent['id']) is None
