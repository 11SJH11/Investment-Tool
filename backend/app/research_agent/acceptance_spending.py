"""One lifetime acceptance allowance per Ledger database; no automatic refunds."""
from contextlib import closing
import json
from uuid import uuid4

from .spending import limit_microusd, usage_cost


class AcceptanceSpending:
    def __init__(self, database, limit):
        self.database = database
        self.limit = limit_microusd(limit)
        if not 0 < self.limit <= 5_000_000:
            raise ValueError('Acceptance allowance must be positive and at most USD 5')
        with closing(database.connect()) as c, c:
            c.execute('CREATE TABLE IF NOT EXISTS agent_acceptance_allowance(id INTEGER PRIMARY KEY CHECK(id=1),limit_microusd INTEGER NOT NULL)')
            c.execute('''CREATE TABLE IF NOT EXISTS agent_acceptance_calls(
                id TEXT PRIMARY KEY,reserved_microusd INTEGER NOT NULL,pricing TEXT NOT NULL,
                usage TEXT,status TEXT NOT NULL DEFAULT 'RESERVED')''')
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT limit_microusd FROM agent_acceptance_allowance WHERE id=1').fetchone()
            if old and old[0]!=self.limit:
                raise ValueError('Acceptance allowance is immutable; do not reset or increase it')
            c.execute('INSERT OR IGNORE INTO agent_acceptance_allowance VALUES(1,?)',(self.limit,))

    def reserve(self, pricing):
        amount=pricing.get('call_reservation_microusd') if pricing else None
        if type(amount) is not int or amount<=0:
            raise ValueError('Acceptance requires conservative model pricing')
        with closing(self.database.connect()) as c, c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM agent_acceptance_calls WHERE status='EXCEEDED'").fetchone():
                raise ValueError('Acceptance usage exceeded reservation; further calls blocked')
            total=c.execute('SELECT COALESCE(SUM(reserved_microusd),0) FROM agent_acceptance_calls').fetchone()[0]
            if total+amount>self.limit:
                raise ValueError('Acceptance USD budget exhausted including reserved calls')
            identifier=str(uuid4())
            c.execute('INSERT INTO agent_acceptance_calls(id,reserved_microusd,pricing) VALUES(?,?,?)',
                      (identifier,amount,json.dumps(pricing,allow_nan=False)))
        return identifier

    def finish(self, identifier, usage):
        with closing(self.database.connect()) as c, c:
            c.execute('BEGIN IMMEDIATE')
            raw=c.execute('SELECT pricing FROM agent_acceptance_calls WHERE id=?',(identifier,)).fetchone()
            pricing=json.loads(raw[0])
            safe={k:usage[k] for k in ('input_tokens','output_tokens') if type(usage.get(k)) is int and usage[k]>=0}
            excessive=any(safe.get(k,0)>pricing[bound] for k,bound in
                          (('input_tokens','input_token_reservation'),('output_tokens','output_token_reservation')))
            cost=usage_cost(safe,pricing)
            c.execute('UPDATE agent_acceptance_calls SET usage=?,status=? WHERE id=?',
                      (json.dumps(safe),'EXCEEDED' if excessive else 'RETURNED' if cost is not None else 'USAGE_UNKNOWN',identifier))
        if excessive:raise ValueError('Acceptance usage exceeded reservation')

    def report(self):
        return self.read_report(self.database)

    @staticmethod
    def read_report(database):
        with closing(database.connect()) as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_acceptance_allowance'").fetchone():
                return None
            limit=c.execute('SELECT limit_microusd FROM agent_acceptance_allowance WHERE id=1').fetchone()
            if not limit:return None
            rows=c.execute('SELECT reserved_microusd,pricing,usage,status FROM agent_acceptance_calls').fetchall()
        costs=[usage_cost(json.loads(r[2]),json.loads(r[1])) if r[2] else None for r in rows]
        return dict(limit_usd=limit[0]/1e6,reserved_usd=sum(r[0] for r in rows)/1e6,
                    usage_estimate_usd=sum(v for v in costs if v is not None)/1e6,
                    calls=len(rows),unknown_usage_calls=sum(v is None for v in costs),
                    invoice_verified=False,automatic_refunds=False)
