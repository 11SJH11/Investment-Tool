"""Positive-evidence reconciliation of a known broker order, never retry authority.

Consumes canonical executions and a complete caller-verified open-position map.
Unknown submissions without a broker order ID remain unresolved. No comment,
price/time proximity or symbol-only matching is used to invent an identity.
"""
from decimal import Decimal

from app.brokers.executions import number
from app.brokers.base import BrokerHistoryError


def reconcile_order(intent, executions, open_positions, *, broker_order_id,
                    account_key, environment, complete):
    def result(state, **details):
        return dict(state=state, retry_allowed=False, execution_enabled=False, **details)

    if (environment != 'demo' or intent['environment'] != 'demo'
            or account_key != intent['account_key']):
        return result('IDENTITY_CONFLICT')
    if complete is not True or not broker_order_id:
        return result('UNRESOLVED')
    # The caller must verify freshness and completeness with the broker before
    # setting complete. A stable history batch alone does not authorize a send.
    if any((e.provider, e.account_key, e.environment) != ('mt5', account_key, environment)
           for e in executions):
        return result('IDENTITY_CONFLICT')
    entries = [e for e in executions if e.order_id == str(broker_order_id) and e.role == 'entry']
    if not entries:
        return result('UNRESOLVED')
    positions = {e.position_id for e in entries}
    if len(positions) != 1 or None in positions or '' in positions:
        return result('EVIDENCE_CONFLICT')
    position_id = next(iter(positions))
    fills = [e for e in executions if e.position_id == position_id]
    if len({e.external_id for e in fills}) != len(fills):
        return result('EVIDENCE_CONFLICT')
    request = intent['request']
    opposite = 'sell' if request['side'] == 'buy' else 'buy'
    if any(e.symbol != request['symbol'] or e.quantity_unit != 'lots'
           or e.role not in {'entry', 'exit'}
           or e.side != (request['side'] if e.role == 'entry' else opposite)
           or (e.role == 'entry' and e.order_id != str(broker_order_id)) for e in fills):
        # Includes netting/scale-in from another order: never silently attribute
        # another strategy's volume to this request.
        return result('EVIDENCE_CONFLICT')
    try:
        quantities = [number(e.quantity) for e in fills]
        requested = number(request['quantity_lots'])
        if requested <= 0 or any(q <= 0 for q in quantities):
            return result('EVIDENCE_CONFLICT')
        entered = sum((number(e.quantity) for e in entries), Decimal(0))
        exited = sum((number(e.quantity) for e in fills if e.role == 'exit'), Decimal(0))
        if entered > requested or exited > entered:
            return result('EVIDENCE_CONFLICT')
        remaining = entered - exited
        details = dict(position_id=position_id, filled_lots=str(entered), exited_lots=str(exited),
                       remaining_lots=str(remaining))
        position = open_positions.get(position_id)
        if remaining == 0:
            if position is not None:
                return result('EVIDENCE_CONFLICT')
            return result('CLOSED' if entered == requested else 'PARTIAL_CLOSED', **details)
        if position is None:
            return result('UNRESOLVED', **details)
        if (position['symbol'] != request['symbol'] or position['side'] != request['side']
                or number(position['quantity_lots']) != remaining):
            return result('EVIDENCE_CONFLICT')
        if (number(position['stop']) != number(request['stop'])
                or number(position['target']) != number(request['target'])):
            return result('PROTECTION_UNVERIFIED', **details)
        return result('FILLED_PROTECTED' if entered == requested else 'PARTIAL_PROTECTED', **details)
    except (BrokerHistoryError, ValueError, TypeError, KeyError):
        return result('EVIDENCE_CONFLICT')
