"""Guarded demo gateway diagnostics. No submission or terminal initialization.

Caller owns the existing terminal/profile lifecycle locks. This composes the
canonical broker checks, sizing and account-wide risk observation, without
accepting caller-supplied risk totals or promoting observations to reconciled.
"""
from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_order_preparation import prepare
from app.brokers.mt5_risk_observation import observe, gross_exposure


def inspect_intent(adapter, ledger, policy_id, intent_id, *, risk_percent,
                   session_key, magic, deviation_points):
    ledger._manual_only()
    if not isinstance(session_key, str) or not 1 <= len(session_key) <= 128:
        raise ValueError('Invalid execution session identity')
    with ledger.account_guard(policy_id):
        policies = ledger.policies()
        policy = next(p['policy'] for p in policies if p['id'] == policy_id)
        intent = next((i for i in ledger.intents(policy_id) if i['id'] == intent_id), None)
        if intent is None or intent['state'] != 'DRAFT':
            raise ValueError('Inspection requires an unused intent from this policy')
        if adapter.account_key != policy['account_key'] or adapter.currency != policy['currency']:
            raise ValueError('Terminal account does not match execution policy')
        draft = intent['request']
        checked = prepare(adapter, dict(symbol=draft['symbol'], side=draft['side'],
            stop=draft['stop'], target=draft['target'], risk_percent=risk_percent),
            intent_id=intent_id, magic=magic, deviation_points=deviation_points)
        if checked['status'] != 'broker_check_passed':
            return dict(status='broker_check_rejected', preparation=checked,
                        execution_enabled=False, orders_sent=False)
        sizing = checked['preflight']['sizing']
        # Never silently resize or reprice an immutable draft during inspection.
        if any(sizing[field] != draft[field] for field in
               ('symbol', 'side', 'entry', 'stop', 'quantity_lots')):
            raise ValueError('Fresh broker sizing differs from the immutable draft')
        account_intents = [i for p in policies if p['policy']['account_key'] == policy['account_key']
                           for i in ledger.intents(p['id'])]
        attempted = [i for i in account_intents if ledger.attempt(i['id']) is not None]
        # Until session attribution/recovery is implemented, count all historical
        # attempts conservatively; never represent an unknown session count as 0.
        session_entries = sum(i['strategy_key'] == policy['strategy_key'] for i in attempted)
        facts = observe(adapter, strategy_key=policy['strategy_key'], session_key=session_key,
                        session_entries=session_entries, unresolved_submissions=len(attempted))
        now_ms = int(adapter._clock() * 1000)
        if not 0 <= now_ms - checked['preflight']['quote_time_msc'] <= 5000:
            raise BrokerHistoryError('MT5 preparation expired during account observation', category='configuration')
        proposed = dict(symbol=draft['symbol'], estimated_stop_risk=sizing['actual_estimated_risk'],
                        estimated_margin=sizing['estimated_margin'],
                        gross_exposure=gross_exposure(adapter._module, draft['symbol'],
                            sizing['quantity_lots'], sizing['entry'], policy['currency']))
        assessment = ledger.assess_risk(policy_id, facts, proposed, now_ms=now_ms,
                                        session_key=session_key)
        return dict(status='diagnostics_complete', preparation=checked, assessment=assessment,
                    count_basis='all_historical_attempts_conservative',
                    execution_enabled=False, orders_sent=False,
                    remaining_gates=['account_reconciliation', 'verified_session_timing',
                                     'submission_authorization', 'protection_and_recovery'])
