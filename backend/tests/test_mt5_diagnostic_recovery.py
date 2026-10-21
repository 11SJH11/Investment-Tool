import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger, policy, order
from tests.test_mt5_execution_coordinator import gateway, prepared, context, run


def fail(ledger, policy_id, **kwargs):
    with pytest.raises(RuntimeError):
        with ledger.account_guard(policy_id, **kwargs):
            raise RuntimeError('private-provider-error')


def test_failed_diagnostic_can_recover_then_repeat(gateway):
    ledger, adapter, p, intent, prepared = gateway
    adapter.account_key = 'c'*64
    with pytest.raises(ValueError):
        run(gateway)
    assert ledger.recover_failed_diagnostic(p['id']) == dict(status='diagnostic_recovered', execution_enabled=False)
    adapter.account_key = 'a'*64
    assert run(gateway)['status'] == 'diagnostics_complete'
    assert ledger.intents(p['id']) == [intent]
    assert ledger.attempt(intent['id']) is None
    with ledger.database.connect() as c:
        row = c.execute('SELECT * FROM mt5_execution_readonly_guards').fetchone()
        assert row['state'] == 'RECOVERED' and row['recovered_at']
        assert 'private-provider-error' not in str(dict(row))


def test_readonly_guard_cannot_begin_attempt(ledger):
    p = ledger.configure(policy())
    intent = ledger.draft(p['id'], order())
    with ledger.account_guard(p['id'], read_only=True) as token:
        with pytest.raises(ValueError, match='Read-only'):
            ledger.begin_attempt(intent['id'], guard_token=token)
    assert ledger.attempt(intent['id']) is None
    assert ledger.account_guard_status(p['id'])['state'] == 'IDLE'


def test_untyped_failure_cannot_be_recovered_as_diagnostic(ledger):
    p = ledger.configure(policy())
    fail(ledger, p['id'])
    with pytest.raises(ValueError, match='reconciliation'):
        ledger.recover_failed_diagnostic(p['id'])


def test_active_diagnostic_cannot_be_recovered(ledger):
    p = ledger.configure(policy())
    with ledger.account_guard(p['id'], read_only=True):
        with pytest.raises(ValueError, match='reconciliation'):
            ledger.recover_failed_diagnostic(p['id'])


def test_restart_preserves_finished_failure_evidence_and_fences_old_owner(ledger):
    p = ledger.configure(policy())
    fail(ledger, p['id'], read_only=True)
    restarted = MT5ExecutionLedger(ledger.database)
    with pytest.raises(ValueError, match='superseded'):
        ledger.recover_failed_diagnostic(p['id'])
    assert restarted.recover_failed_diagnostic(p['id'])['status'] == 'diagnostic_recovered'
    assert not restarted.policies()[0]['enabled']
    assert restarted.recover_failed_diagnostic(p['id'])['status'] == 'already_idle'


def test_restart_does_not_convert_active_check_to_finished_evidence(ledger):
    p = ledger.configure(policy())
    with pytest.raises(ValueError, match='superseded'):
        with ledger.account_guard(p['id'], read_only=True):
            restarted = MT5ExecutionLedger(ledger.database)
            with pytest.raises(ValueError, match='reconciliation'):
                restarted.recover_failed_diagnostic(p['id'])
    with pytest.raises(ValueError, match='reconciliation'):
        restarted.recover_failed_diagnostic(p['id'])


def test_any_account_attempt_blocks_diagnostic_recovery(ledger):
    p = ledger.configure(policy())
    intent = ledger.draft(p['id'], order())
    with ledger.account_guard(p['id']) as token:
        ledger.begin_attempt(intent['id'], guard_token=token)
    # Fixture-only removal to test defense beyond the normal guard barrier.
    with ledger.database.connect() as c:
        c.execute('DELETE FROM mt5_execution_account_guards')
    other = ledger.configure(policy() | {'strategy_key': 'other'})
    fail(ledger, other['id'], read_only=True)
    with pytest.raises(ValueError, match='reconciliation'):
        ledger.recover_failed_diagnostic(other['id'])


def test_research_and_live_cannot_recover(ledger):
    from app.research_agent.access import preparation_scope
    p = ledger.configure(policy())
    fail(ledger, p['id'], read_only=True)
    with preparation_scope(ledger.database, 'fixture'):
        with pytest.raises(ValueError, match='Research'):
            ledger.recover_failed_diagnostic(p['id'])
    live = ledger.configure(policy() | {'environment': 'live'})
    with pytest.raises(ValueError, match='demo'):
        ledger.recover_failed_diagnostic(live['id'])


def test_recovery_does_not_undo_emergency_stop(ledger):
    p = ledger.configure(policy())
    fail(ledger, p['id'], read_only=True)
    ledger.emergency_stop()
    ledger.recover_failed_diagnostic(p['id'])
    assert ledger.policies()[0]['status'] == 'EMERGENCY_STOP'
    with pytest.raises(ValueError, match='disabled'):
        ledger.authorize_submission()
