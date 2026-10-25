"""Bounded, persisted read-only account observations. Never strategy attribution."""
from contextlib import closing
from datetime import datetime, timezone
import json


def _schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS mt5_account_observations(account_key TEXT PRIMARY KEY, environment TEXT NOT NULL, document TEXT, last_attempt_at TEXT NOT NULL, error_category TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS mt5_account_equity_observations(id INTEGER PRIMARY KEY AUTOINCREMENT, account_key TEXT NOT NULL, environment TEXT NOT NULL, observed_at TEXT NOT NULL, document TEXT NOT NULL)')
    c.execute('CREATE INDEX IF NOT EXISTS mt5_account_equity_page ON mt5_account_equity_observations(account_key,id)')


def save(database, snapshot):
    key,environment=snapshot['account_key'],snapshot['environment']
    # Input is the canonical MT5 account allowlist, never raw terminal/provider data.
    summary={**snapshot['account'], 'position_count':len(snapshot['positions']), 'pending_order_count':len(snapshot['pending_orders'])}
    with closing(database.connect()) as c, c:
        _schema(c)
        c.execute('INSERT INTO mt5_account_observations VALUES(?,?,?,?,NULL) ON CONFLICT(account_key) DO UPDATE SET environment=excluded.environment,document=excluded.document,last_attempt_at=excluded.last_attempt_at,error_category=NULL',
                  (key,environment,json.dumps(snapshot,allow_nan=False),snapshot['observed_at']))
        c.execute('INSERT INTO mt5_account_equity_observations(account_key,environment,observed_at,document) VALUES(?,?,?,?)',
                  (key,environment,snapshot['observed_at'],json.dumps(summary,allow_nan=False)))
        c.execute('DELETE FROM mt5_account_equity_observations WHERE account_key=? AND id NOT IN (SELECT id FROM mt5_account_equity_observations WHERE account_key=? ORDER BY id DESC LIMIT 1000)',(key,key))
        c.execute('DELETE FROM mt5_account_equity_observations WHERE id <= COALESCE((SELECT id FROM mt5_account_equity_observations ORDER BY id DESC LIMIT 1 OFFSET 10000),-1)')


def failed(database, key, environment):
    with closing(database.connect()) as c, c:
        _schema(c)
        c.execute('INSERT INTO mt5_account_observations VALUES(?,?,NULL,?,?) ON CONFLICT(account_key) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,error_category=excluded.error_category',
                  (key,environment,datetime.now(timezone.utc).isoformat(),'snapshot_unavailable'))


def read(database, key, environment, *, history=False):
    result=dict(snapshot=None,last_attempt_at=None,error_category=None,history=[])
    if not key:return result
    with closing(database.connect()) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_account_observations'").fetchone():return result
        row=c.execute('SELECT document,last_attempt_at,error_category FROM mt5_account_observations WHERE account_key=? AND environment=?',(key,environment)).fetchone()
        if not row:return result
        result.update(snapshot=json.loads(row[0]) if row[0] else None,last_attempt_at=row[1],error_category=row[2])
        if history:
            rows=c.execute('SELECT id,observed_at,document FROM mt5_account_equity_observations WHERE account_key=? AND environment=? ORDER BY id DESC LIMIT 1000',(key,environment)).fetchall()
            result['history']=[dict(json.loads(r[2]),id=r[0],observed_at=r[1]) for r in reversed(rows)]
    return result
