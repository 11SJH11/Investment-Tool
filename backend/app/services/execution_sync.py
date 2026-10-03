"""Shared canonical execution -> Journal reconciliation for new history adapters."""
from threading import Lock

from app.brokers.base import BrokerHistoryError, HistoryBatch
from app.brokers.executions import Execution, closed_positions
from app.storage.broker_sync_repository import BrokerSyncRepository

_guard = Lock()
_locks = {}


def reconcile(adapter, database):
    repo = BrokerSyncRepository(database)
    with _guard:
        lock = _locks.setdefault((adapter.provider, adapter.account_key), Lock())
    if not lock.acquire(blocking=False):
        raise BrokerHistoryError('A sync is already running for this broker account', category='busy')
    try:
        cursor = repo.state(adapter.provider, adapter.account_key).get('cursor')
        saved = {e['external_id']: e for e in repo.executions(adapter.provider, adapter.account_key)}
        incoming = adapter.read_executions(cursor)
        changed, touched = {}, set()
        seen = {}
        for execution in incoming.executions:
            payload = execution.payload()
            if (execution.provider, execution.account_key) != (adapter.provider, adapter.account_key):
                raise BrokerHistoryError('Execution account does not match the selected account', category='history')
            if execution.external_id in seen and seen[execution.external_id] != payload:
                raise BrokerHistoryError('Conflicting execution identities in one sync', category='history')
            seen[execution.external_id] = payload
            previous = saved.get(execution.external_id)
            if previous and previous['position_id'] != execution.position_id:
                raise BrokerHistoryError('Provider changed an execution position identity; manual reconciliation required', category='history')
            if saved.get(execution.external_id) != payload:
                changed[execution.external_id] = payload
                touched.add(execution.position_id)
        merged = {**saved, **changed}
        # Recheck pending positions when an open-position snapshot changes without
        # changing the order aggregates. Existing closed rows stay idempotent.
        existing_ids = repo.journal_ids(adapter.provider, adapter.account_key)
        for e in merged.values():
            external_id = f'{e["environment"]}:{e["account_key"]}:{e["position_id"]}'
            if external_id not in existing_ids:
                touched.add(e['position_id'])
        fills = [Execution(**e) for e in merged.values() if e['position_id'] in touched]
        trades = closed_positions(fills, adapter.account_label, adapter.currency, incoming.open_position_ids)
        closed_ids = {t['external_id'] for t in trades}
        if any(f'{e.environment}:{e.account_key}:{e.position_id}' in existing_ids - closed_ids for e in fills):
            raise BrokerHistoryError('Correction would invalidate a closed position; manual reconciliation required', category='history')
        result = repo.commit(adapter, HistoryBatch(trades, incoming.cursor, list(changed.values())), cursor)
        return dict(status='success', **result, executions_changed=len(changed))
    finally:
        lock.release()
