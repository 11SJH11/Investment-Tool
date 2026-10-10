from contextlib import closing
from datetime import datetime, timezone
import json

from app.core.journal_fields import REVIEW_FIELDS
from app.storage.journal_repository import TRADE_COLUMNS, _encode


def persist_executions(connection, adapter, executions):
    """Called inside the caller's facts/cursor transaction for either destination."""
    for execution in executions:
        if (execution['provider'], execution['account_key']) != (adapter.provider, adapter.account_key):
            raise ValueError('Execution account does not match sync account')
        connection.execute('''INSERT INTO broker_executions VALUES (?,?,?,?,?)
            ON CONFLICT(provider,account_key,external_id) DO UPDATE SET
            position_id=excluded.position_id,payload=excluded.payload''',
            (adapter.provider, adapter.account_key, execution['external_id'], execution['position_id'],
             json.dumps(execution, allow_nan=False)))


class BrokerSyncRepository:
    def __init__(self, database):
        self.database = database

    def state(self, provider, account_key):
        with closing(self.database.connect()) as connection:
            row = connection.execute("SELECT * FROM broker_sync_state WHERE provider=? AND account_key=?", (provider, account_key)).fetchone()
            return dict(row) if row else {}

    def executions(self, provider, account_key):
        with closing(self.database.connect()) as connection:
            rows = connection.execute('SELECT payload FROM broker_executions WHERE provider=? AND account_key=?',
                                      (provider, account_key)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def journal_ids(self, provider, account_key):
        with closing(self.database.connect()) as connection:
            return {r[0] for r in connection.execute(
                'SELECT external_id FROM journal_trades WHERE external_provider=? AND external_account_key=?',
                (provider, account_key))}

    def failure(self, adapter, error):
        with closing(self.database.connect()) as connection, connection:
            connection.execute("""INSERT INTO broker_sync_state(provider,account_key,environment,status,error)
                VALUES (?,?,?,'error',?) ON CONFLICT(provider,account_key) DO UPDATE SET status='error',error=excluded.error""",
                (adapter.provider, adapter.account_key, adapter.environment, error))

    def commit(self, adapter, batch, expected_cursor):
        created = updated = 0
        with closing(self.database.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute("SELECT cursor FROM broker_sync_state WHERE provider=? AND account_key=?", (adapter.provider, adapter.account_key)).fetchone()
            if (state[0] if state else None) != expected_cursor:
                raise ValueError("Another sync completed; retry to read the latest history")
            persist_executions(connection, adapter, batch.executions)
            for data in batch.trades:
                from app.core.automation import automation_fields
                data = {**data, **automation_fields(data)}
                # Legacy schema requires a fees number. Canonical unknown costs
                # retain their null evidence and are decoded as null at every
                # Journal read boundary, never presented as zero-cost trading.
                if data.get('fees') is None and data.get('source_metadata', {}).get('canonical_execution_version') == 1:
                    data = {**data, 'fees': 0}
                existing = connection.execute("SELECT * FROM journal_trades WHERE source=? AND external_provider=? AND external_id=?", (data["source"], data["external_provider"], data["external_id"])).fetchone()
                if existing:
                    # Never replace discretionary fields, even when the adapter
                    # accidentally includes a same-named field in its payload.
                    fields = [k for k in TRADE_COLUMNS if k in data and k not in REVIEW_FIELDS and k != "imported_at"]
                    previous = json.loads(existing["source_metadata"] or "{}")
                    current = dict(data["source_metadata"])
                    current["original_import"] = previous.get("original_import", previous)
                    data = {**data, "source_metadata": current}
                    connection.execute(f"UPDATE journal_trades SET {','.join(k+'=?' for k in fields)},updated_at=CURRENT_TIMESTAMP WHERE id=?", (*[_encode(data[k], k) for k in fields], existing["id"]))
                    updated += 1
                else:
                    # Review fields start empty; provider adapters do not own them.
                    values = [_encode(None if k in REVIEW_FIELDS else data.get(k), k) for k in TRADE_COLUMNS]
                    connection.execute(f"INSERT INTO journal_trades({','.join(TRADE_COLUMNS)}) VALUES ({','.join('?' for _ in TRADE_COLUMNS)})", values)
                    created += 1
            connection.execute("""INSERT INTO broker_sync_state(provider,account_key,environment,cursor,last_success_at,status,error)
                VALUES (?,?,?,?,?,'success',NULL) ON CONFLICT(provider,account_key) DO UPDATE SET
                cursor=excluded.cursor,last_success_at=excluded.last_success_at,status='success',error=NULL""",
                (adapter.provider, adapter.account_key, adapter.environment, batch.cursor, datetime.now(timezone.utc).isoformat()))
        return {"created": created, "updated": updated, "cursor": batch.cursor}
