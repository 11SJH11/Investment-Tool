from contextlib import closing
from datetime import datetime, timezone
import json


class PortfolioBrokerRepository:
    def __init__(self, database):
        self.database = database

    def commit(self, adapter, snapshot, expected_cursor, profile_binding=None):
        stamp = datetime.now(timezone.utc).isoformat()
        created = updated = 0
        with closing(self.database.connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            previous = c.execute("SELECT cursor FROM broker_sync_state WHERE provider=? AND account_key=?",
                                 (adapter.provider, adapter.account_key)).fetchone()
            if (previous[0] if previous else None) != expected_cursor:
                raise ValueError("Another sync completed; retry")
            c.execute("""INSERT INTO portfolio_broker_accounts VALUES (?,?,?,?,?,?)
                ON CONFLICT(provider,account_key) DO UPDATE SET summary=excluded.summary,synced_at=excluded.synced_at""",
                (adapter.provider, adapter.account_key, adapter.environment, adapter.account_label,
                 json.dumps(snapshot.summary, allow_nan=False), stamp))
            c.execute("UPDATE portfolio_broker_records SET active=0 WHERE provider=? AND account_key=? AND kind='position'",
                      (adapter.provider, adapter.account_key))
            seen = {}
            for row in snapshot.positions + snapshot.events:
                identity = (adapter.provider, adapter.account_key, row['kind'], row['external_id'])
                if identity in seen:
                    if seen[identity] != row['facts']:
                        raise ValueError('Conflicting provider records during pagination')
                    continue
                seen[identity] = row['facts']
                exists = c.execute("SELECT id FROM portfolio_broker_records WHERE provider=? AND account_key=? AND kind=? AND external_id=?", identity).fetchone()
                c.execute("""INSERT INTO portfolio_broker_records(provider,account_key,kind,external_id,facts) VALUES (?,?,?,?,?)
                    ON CONFLICT(provider,account_key,kind,external_id) DO UPDATE SET facts=excluded.facts,active=1""",
                    (*identity, json.dumps(row['facts'], allow_nan=False)))
                if exists: updated += 1
                else: created += 1
            # No inferred high-watermark: full scans retain corrections and late postings.
            c.execute("""INSERT INTO broker_sync_state(provider,account_key,environment,cursor,last_success_at,status,error)
                VALUES (?,?,?,?,?,'success',NULL) ON CONFLICT(provider,account_key) DO UPDATE SET
                cursor=excluded.cursor,last_success_at=excluded.last_success_at,status='success',error=NULL""",
                (adapter.provider, adapter.account_key, adapter.environment, stamp, stamp))
            if profile_binding:
                c.execute("""INSERT INTO app_settings(key,value) VALUES (?,?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
                    (profile_binding, adapter.account_key))
        return {"created": created, "updated": updated, "status": "success", "account_key": adapter.account_key}

    def accounts(self):
        with closing(self.database.connect()) as c:
            rows = c.execute("SELECT * FROM portfolio_broker_accounts ORDER BY label").fetchall()
        return [{**dict(r), "summary": json.loads(r['summary'])} for r in rows]

    def records(self, account_key, kind=None, limit=100, offset=0):
        clauses, args = ["account_key=?", "provider='trading212'"], [account_key]
        if kind:
            clauses.append("kind=?"); args.append(kind)
        where = ' AND '.join(clauses)
        with closing(self.database.connect()) as c:
            total = c.execute(f"SELECT COUNT(*) FROM portfolio_broker_records WHERE {where}", args).fetchone()[0]
            rows = c.execute(f"SELECT * FROM portfolio_broker_records WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return {"total": total, "items": [{**dict(r), "facts": json.loads(r['facts']), "tags": json.loads(r['tags'])} for r in rows]}

    def review(self, record_id, note, tags):
        with closing(self.database.connect()) as c, c:
            return c.execute("UPDATE portfolio_broker_records SET note=?,tags=? WHERE id=?",
                             (note, json.dumps(tags), record_id)).rowcount > 0
