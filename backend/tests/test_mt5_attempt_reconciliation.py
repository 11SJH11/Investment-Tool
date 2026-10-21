from dataclasses import replace

import pytest

from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
from tests.test_mt5_execution_ledger import ledger, policy, order
from tests.test_mt5_execution_reconciliation import execution


def setup(ledger, ticket='100'):
    p = ledger.configure(policy())
    intent = ledger.draft(p['id'], order())
    with ledger.account_guard(p['id']) as token:
        attempt = ledger.begin_attempt(intent['id'], guard_token=token)
        if ticket is not None:
            ledger.record_attempt_receipt(attempt['id'], guard_token=token,
                                          retcode=10009, broker_order_id=ticket)
    return p, intent


def reconcile(ledger, intent, **changes):
    args = dict(account_key='a'*64, environment='demo', complete=True, observed_at_ms=1000)
    args.update(changes)
    return ledger.reconcile_attempt(intent['id'], [execution()],
        {'200': dict(symbol='XAUUSDs', side='buy', quantity_lots=.1, stop=2990., target=3020.)}, **args)


def test_receipt_identity_reconciles_and_survives_restart_without_unlocking(ledger):
    p, intent = setup(ledger)
    result = reconcile(ledger, intent)
    assert result['broker_order_id'] == '100'
    assert result['decision']['state'] == 'FILLED_PROTECTED'
    assert result['identity_basis'] == 'durable_attempt_receipt'
    assert result == reconcile(ledger, intent)
    assert len(ledger.reconciliations(intent['id'])) == 1
    restarted = MT5ExecutionLedger(ledger.database)
    attempt = restarted.attempt(intent['id'])
    assert attempt['latest_reconciliation']['id'] == result['id']
    assert attempt['state'] == 'SUBMISSION_UNCERTAIN'
    assert restarted.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'
    with pytest.raises(ValueError, match='superseded'):
        reconcile(ledger, intent)


@pytest.mark.parametrize('ticket', [None, '999'])
def test_missing_or_unmatched_saved_ticket_never_guessed(ledger, ticket):
    _, intent = setup(ledger, ticket)
    assert reconcile(ledger, intent)['decision']['state'] == 'UNRESOLVED'


def test_older_observation_retained_without_replacing_latest(ledger):
    _, intent = setup(ledger)
    newer = reconcile(ledger, intent, observed_at_ms=2000, complete=False)
    reconcile(ledger, intent, observed_at_ms=1000)
    assert ledger.attempt(intent['id'])['latest_reconciliation']['id'] == newer['id']
    assert len(ledger.reconciliations(intent['id'])) == 2


def test_alternate_ticket_cannot_override_saved_receipt(ledger):
    _, intent = setup(ledger)
    with pytest.raises(ValueError, match='alternate'):
        ledger.record_reconciliation(intent['id'], [], {}, broker_order_id='999',
            account_key='a'*64, environment='demo', complete=True, observed_at_ms=1000,
            use_attempt_receipt=True)
    assert ledger.reconciliations(intent['id']) == []


@pytest.mark.parametrize('changes', [{'account_key': 'c'*64}, {'environment': 'live'}])
def test_wrong_account_or_environment_is_conflict(ledger, changes):
    _, intent = setup(ledger)
    assert reconcile(ledger, intent, **changes)['decision']['state'] == 'IDENTITY_CONFLICT'


def test_closed_evidence_is_recorded_without_resend_permission(ledger):
    p, intent = setup(ledger)
    exit_fill = replace(execution('2'), order_id='101', side='sell', role='exit')
    result = ledger.reconcile_attempt(intent['id'], [execution(), exit_fill], {},
        account_key='a'*64, environment='demo', complete=True, observed_at_ms=1000)
    assert result['decision']['state'] == 'CLOSED'
    assert not result['decision']['retry_allowed']
    assert ledger.account_guard_status(p['id'])['state'] == 'RECONCILIATION_REQUIRED'


def test_plain_draft_has_no_receipt_identity(ledger):
    p = ledger.configure(policy())
    intent = ledger.draft(p['id'], order())
    with pytest.raises(ValueError, match='No durable'):
        reconcile(ledger, intent)
