import os
import subprocess
import sys

import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from app.storage.database import Database
from tests.test_mt5_execution_ledger import ledger, policy, order


def setup(ledger):
    p = ledger.configure(policy())
    return p, ledger.draft(p['id'], order())


def test_write_ahead_marker_retains_guard_even_on_normal_return(ledger):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
        assert ledger.attempt(intent['id']) == attempt
        assert ledger.intents(p['id'])[0]['state'] == 'SUBMISSION_UNCERTAIN'
        assert not attempt['execution_enabled']
        with pytest.raises(ValueError, match='unused'):
            ledger.begin_attempt(intent['id'], guard_token=token)
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError, match='reconciliation'):
        with ledger.account_guard(p['id']):
            pytest.fail('An uncertain attempt must block the whole account')
    with pytest.raises(ValueError, match='disabled'):
        ledger.authorize_submission(attempt['id'])


@pytest.mark.parametrize('retcode', [0, 10009, 10010, 10019, 10031])
def test_receipt_is_evidence_not_fill_or_retry_permission(ledger, retcode):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
        result = ledger.record_attempt_receipt(attempt['id'], guard_token=token,
                                              retcode=retcode, broker_order_id='00100')
        assert result['receipt'] == dict(retcode=retcode, broker_order_id='100')
        assert result['state'] == 'SUBMISSION_UNCERTAIN'
        assert result == ledger.record_attempt_receipt(attempt['id'], guard_token=token,
                                                       retcode=retcode, broker_order_id='100')
        with pytest.raises(ValueError, match='immutable'):
            ledger.record_attempt_receipt(attempt['id'], guard_token=token, retcode=retcode,
                                          broker_order_id='101')
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_wrong_token_and_account_cannot_create_attempt(ledger):
    p, intent = setup(ledger)
    other = ledger.configure(policy() | {'account_key': 'c'*64})
    with ledger.account_guard(other['id']) as token:
        with pytest.raises(ValueError, match='guard'):
            ledger.begin_attempt(intent['id'], guard_token=token)
    assert ledger.attempt(intent['id']) is None
    assert ledger.intents(p['id']) == [intent]


def test_emergency_stop_prevents_new_attempt_but_preserves_late_receipt(ledger):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        ledger.emergency_stop()
        with pytest.raises(ValueError, match='emergency'):
            ledger.begin_attempt(intent['id'], guard_token=token)
    # Separate account fixture for an already-started attempt.
    second = ledger.configure(policy() | {'account_key': 'c'*64})
    draft = ledger.draft(second['id'], order())
    with ledger.account_guard(second['id']) as token:
        attempt = ledger.begin_attempt(draft['id'], guard_token=token)
        ledger.emergency_stop()
        result = ledger.record_attempt_receipt(attempt['id'], guard_token=token, retcode=10009)
        assert result['receipt']['broker_order_id'] is None
        assert not ledger.policies()[1]['enabled']


def test_restart_retains_attempt_and_fences_late_old_process_response(ledger):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
    restarted = MT5ExecutionLedger(ledger.database)
    assert restarted.attempt(intent['id']) == attempt
    with pytest.raises(ValueError, match='superseded'):
        ledger.record_attempt_receipt(attempt['id'], guard_token=token, retcode=10009)
    with pytest.raises(ValueError, match='original'):
        restarted.record_attempt_receipt(attempt['id'], guard_token=token, retcode=10009)
    assert restarted.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('kwargs', [dict(retcode=True), dict(retcode=-1),
    dict(retcode=10009, broker_order_id='secret-native-text'), dict(retcode=10009, broker_order_id='0')])
def test_invalid_receipt_never_changes_attempt(ledger, kwargs):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
        with pytest.raises(ValueError):
            ledger.record_attempt_receipt(attempt['id'], guard_token=token, **kwargs)
        assert ledger.attempt(intent['id']) == attempt


def test_research_cannot_create_or_record_attempt(ledger):
    from app.research_agent.access import preparation_scope
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        with preparation_scope(ledger.database, 'fixture'):
            with pytest.raises(ValueError, match='Research'):
                ledger.begin_attempt(intent['id'], guard_token=token)
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
        with preparation_scope(ledger.database, 'fixture'):
            with pytest.raises(ValueError, match='Research'):
                ledger.record_attempt_receipt(attempt['id'], guard_token=token, retcode=10009)


@pytest.mark.parametrize('same_account', [True, False])
def test_broker_ticket_identity_is_account_scoped_and_unique(ledger, same_account):
    p, intent = setup(ledger)
    with ledger.account_guard(p['id']) as token:
        first = ledger.begin_attempt(intent['id'], guard_token=token)
        ledger.record_attempt_receipt(first['id'], guard_token=token, retcode=10009, broker_order_id='100')
    # Fixture-only recovery: no production API is permitted to clear this guard.
    with ledger.database.connect() as c:
        c.execute('DELETE FROM mt5_execution_account_guards')
    other = ledger.configure(policy() | {'strategy_key': 'second',
        'account_key': 'a'*64 if same_account else 'c'*64})
    draft = ledger.draft(other['id'], order())
    with ledger.account_guard(other['id']) as token:
        second = ledger.begin_attempt(draft['id'], guard_token=token)
        if same_account:
            with pytest.raises(ValueError, match='already linked'):
                ledger.record_attempt_receipt(second['id'], guard_token=token,
                                              retcode=10009, broker_order_id='00100')
            assert ledger.attempt(draft['id'])['receipt'] is None
        else:
            ledger.record_attempt_receipt(second['id'], guard_token=token,
                                          retcode=10009, broker_order_id='100')
    assert ledger.attempt(intent['id'])['receipt']['broker_order_id'] == '100'


def test_real_process_death_after_write_ahead_marker(tmp_path):
    dbpath = tmp_path / 'crash.db'
    db = Database(dbpath)
    db.initialize()
    script = '''
import os, sys
from app.storage.database import Database
from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import policy, order
ledger = MT5ExecutionLedger(Database(sys.argv[1]))
p = ledger.configure(policy())
intent = ledger.draft(p['id'], order())
with ledger.account_guard(p['id']) as token:
    ledger.begin_attempt(intent['id'], guard_token=token)
    os._exit(0)
'''
    result = subprocess.run([sys.executable, '-c', script, str(dbpath)],
                            cwd=os.getcwd(), timeout=30, capture_output=True)
    assert result.returncode == 0
    recovered = MT5ExecutionLedger(db)
    p = recovered.configure(policy())
    intent = recovered.intents(p['id'])[0]
    assert recovered.attempt(intent['id'])['receipt'] is None
    assert intent['state'] == 'SUBMISSION_UNCERTAIN'
    assert recovered.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
