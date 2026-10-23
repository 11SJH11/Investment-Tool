"""Read-only recovery evidence using the canonical MT5 history adapter.

Caller owns terminal/profile locks. Two full matching observations are required;
no orders, guessed time offsets, credential reads or terminal switching occur.
This does not authorize execution or release a durable account guard.
"""
from datetime import datetime

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_sizing import finite


def collect(adapter):
    from app.research_agent.access import active
    if active():
        raise BrokerHistoryError('Research cannot collect execution recovery evidence', category='configuration')
    try:
        module = adapter._module
        start = int(adapter._clock() * 1000)
        account, key = adapter._account()
        if (adapter.environment != 'demo' or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or key != adapter.account_key or account.currency != adapter.currency):
            raise ValueError('account_identity')

        def positions():
            rows = module.positions_get()
            if rows is None or len(rows) >= 10000:
                raise ValueError('positions_unavailable')
            result = {}
            for row in rows:
                if type(row.identifier) is not int or row.identifier <= 0:
                    raise ValueError('position_identity')
                identifier = str(row.identifier)
                if identifier in result or row.type not in (module.ORDER_TYPE_BUY, module.ORDER_TYPE_SELL):
                    raise ValueError('conflicting_position')
                info = module.symbol_info(row.symbol)
                if info is None or info.name != row.symbol:
                    raise ValueError('unknown_symbol')
                result[identifier] = dict(symbol=row.symbol,
                    side='buy' if row.type == module.ORDER_TYPE_BUY else 'sell',
                    quantity_lots=finite(row.volume, positive=True),
                    stop=finite(row.sl), target=finite(row.tp))
            return result

        def pending():
            rows = module.orders_get()
            if rows is None or len(rows) >= 10000:
                raise ValueError('orders_unavailable')
            result = {}
            for row in rows:
                if type(row.ticket) is not int or row.ticket <= 0 or str(row.ticket) in result:
                    raise ValueError('order_identity')
                result[str(row.ticket)] = (row.symbol, row.type,
                    finite(row.volume_current), finite(row.price_open), finite(row.sl), finite(row.tp))
            return result

        before_positions, before_orders = positions(), pending()
        first = adapter.read_executions(None)
        second = adapter.read_executions(None)
        after_positions, after_orders = positions(), pending()
        finish = int(adapter._clock() * 1000)
        final_account, final_key = adapter._account()
        if (not 0 <= finish-start <= 5000 or final_key != key or adapter.account_key != key
                or adapter.environment != 'demo' or final_account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or final_account.currency != account.currency or adapter.currency != account.currency):
            raise ValueError('identity_or_snapshot_expired')

        def executions(batch):
            if len(batch.executions) >= 100000:
                raise ValueError('history_budget')
            result = {}
            for execution in batch.executions:
                if (execution.provider, execution.account_key, execution.environment) != ('mt5', key, 'demo'):
                    raise ValueError('execution_identity')
                stamp = datetime.fromisoformat(execution.timestamp.replace('Z', '+00:00'))
                if stamp.utcoffset() is None or not 0 <= stamp.timestamp()*1000 <= start:
                    # Import tolerates bounded skew; execution recovery must not
                    # silently assume those provider epochs mean verified UTC.
                    raise ValueError('unverified_execution_time')
                if execution.external_id in result:
                    raise ValueError('duplicate_execution')
                result[execution.external_id] = execution
            return result

        if (executions(first) != executions(second) or before_positions != after_positions
                or before_orders != after_orders or first.open_position_ids != second.open_position_ids
                or second.open_position_ids != set(after_positions)):
            raise ValueError('broker_state_changed')
        return dict(account_key=key, environment='demo', currency=account.currency,
                    observed_at_ms=start, completed_at_ms=finish, complete=True,
                    executions=second.executions, open_positions=after_positions,
                    pending_order_ids=sorted(after_orders), execution_enabled=False)
    except Exception:
        raise BrokerHistoryError('MT5 recovery snapshot unavailable: verify stable complete history, account and UTC timestamps',
                                 category='history') from None


def reconcile_account(adapter, ledger, policy_id):
    """Collect first, then record receipt-bound evidence for the whole account.

    Results remain observations, not account release or trading permission. A
    failed collection writes no reconciliation rows. Attempts without a saved
    order ID remain unresolved. Caller owns terminal/profile lifecycle locks.
    """
    ledger._manual_only()
    policies = ledger.policies()
    selected = next((p['policy'] for p in policies if p['id'] == policy_id), None)
    if selected is None or selected['environment'] != 'demo' or selected['account_key'] != adapter.account_key:
        raise ValueError('Recovery requires the selected demo account')
    snapshot = collect(adapter)
    if snapshot['currency'] != selected['currency']:
        raise ValueError('Recovery account currency changed')
    records = ledger.reconcile_account_snapshot(policy_id,snapshot['executions'],snapshot['open_positions'],
        account_key=snapshot['account_key'],environment='demo',currency=snapshot['currency'],
        complete=not snapshot['pending_order_ids'],observed_at_ms=snapshot['observed_at_ms'])
    return dict(status='recovery_observed', observations=records,
                deals_retrieved=len(snapshot['executions']), open_positions=len(snapshot['open_positions']),
                pending_orders=len(snapshot['pending_order_ids']), execution_enabled=False,
                account_released=False)
