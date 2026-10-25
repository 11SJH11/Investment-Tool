"""Durable MT5 execution groundwork; no native submission or arming capability.

Policies and drafts are inspectable but cannot authorize a broker call. Future
gateways must establish reconciliation and risk checks before adding that path.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4
from contextlib import contextmanager, nullcontext

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    account_key: str = Field(pattern=r'^[a-f0-9]{64}$')
    environment: Literal['demo', 'live']
    strategy_key: str = Field(min_length=1, max_length=200)
    strategy_source_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    symbols: list[str] = Field(min_length=1, max_length=100)
    max_trade_risk: float = Field(gt=0)
    max_daily_loss: float = Field(gt=0)
    max_positions: int = Field(ge=1, le=100, strict=True)
    max_gross_exposure: float = Field(gt=0)


class DraftIntent(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    request_key: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=256)
    side: Literal['buy', 'sell']
    quantity_lots: float = Field(gt=0)
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    target: float = Field(gt=0)


class MT5ExecutionLedger:
    def __init__(self, database):
        self.database = database
        self.owner = str(uuid4())
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS mt5_execution_owner(id INTEGER PRIMARY KEY CHECK(id=1), owner TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS mt5_execution_policies(id TEXT PRIMARY KEY, document TEXT NOT NULL)')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_intents(
                id TEXT PRIMARY KEY, policy_id TEXT NOT NULL REFERENCES mt5_execution_policies(id),
                request_key TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(policy_id,request_key))''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_risk_assessments(
                id TEXT PRIMARY KEY, policy_id TEXT NOT NULL REFERENCES mt5_execution_policies(id),
                document TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_reconciliations(
                id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES mt5_execution_intents(id),
                document TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_attempts(
                id TEXT PRIMARY KEY, intent_id TEXT NOT NULL UNIQUE REFERENCES mt5_execution_intents(id),
                account_key TEXT NOT NULL, broker_order_id TEXT, document TEXT NOT NULL,
                UNIQUE(account_key, broker_order_id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_account_guards(
                account_key TEXT PRIMARY KEY, owner TEXT NOT NULL, token TEXT NOT NULL,
                state TEXT NOT NULL, created_at TEXT NOT NULL)''')
            c.execute('''CREATE TABLE IF NOT EXISTS mt5_execution_readonly_guards(
                token TEXT PRIMARY KEY, account_key TEXT NOT NULL, state TEXT NOT NULL,
                created_at TEXT NOT NULL, recovered_at TEXT)''')
            c.execute('BEGIN IMMEDIATE')
            # A crash can occur after a broker accepted a request but before its
            # response was saved. Never expire or silently steal that authority.
            c.execute("UPDATE mt5_execution_account_guards SET state='RECONCILIATION_REQUIRED'")
            c.execute('INSERT INTO mt5_execution_owner VALUES(1,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner', (self.owner,))
            for row in c.execute('SELECT id,document FROM mt5_execution_policies').fetchall():
                item=json.loads(row['document'])
                item.update(enabled=False,reconciled=False,status='RESTART_RECONCILIATION_REQUIRED')
                c.execute('UPDATE mt5_execution_policies SET document=? WHERE id=?',(encoded(item),row['id']))

    def _owns(self,c):
        row=c.execute('SELECT owner FROM mt5_execution_owner WHERE id=1').fetchone()
        if not row or row['owner']!=self.owner:
            raise ValueError('MT5 execution ledger was superseded by a newer process')

    @staticmethod
    def _manual_only():
        from app.research_agent.access import active
        if active():raise ValueError('Research cannot configure execution policies or create execution intents')

    def configure(self, request):
        self._manual_only()
        policy=RiskPolicy.model_validate(request).model_dump()
        if len(set(policy['symbols']))!=len(policy['symbols']) or any(not s.strip() or len(s)>256 for s in policy['symbols']):
            raise ValueError('Policy symbols must be unique broker names')
        policy['symbols']=sorted(policy['symbols'])
        identifier=sha256(encoded(policy).encode()).hexdigest()
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');self._owns(c)
            row=c.execute('SELECT document FROM mt5_execution_policies WHERE id=?',(identifier,)).fetchone()
            if row:return json.loads(row['document'])
            item=dict(id=identifier,policy=policy,enabled=False,reconciled=False,
                      status='DISABLED',created_at=datetime.now(timezone.utc).isoformat())
            c.execute('INSERT INTO mt5_execution_policies VALUES(?,?)',(identifier,encoded(item)))
            return item

    def policies(self):
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM mt5_execution_policies ORDER BY rowid')]

    def draft(self,policy_id,request):
        self._manual_only()
        request=DraftIntent.model_validate(request).model_dump()
        long=request['side']=='buy'
        if not (request['stop']<request['entry']<request['target'] if long else request['target']<request['entry']<request['stop']):
            raise ValueError('Draft stop/target direction is invalid')
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');self._owns(c)
            row=c.execute('SELECT document FROM mt5_execution_policies WHERE id=?',(policy_id,)).fetchone()
            if not row:raise ValueError('Unknown MT5 execution policy')
            policy=json.loads(row[0])['policy']
            if request['symbol'] not in policy['symbols']:raise ValueError('Symbol outside policy')
            row=c.execute('SELECT document FROM mt5_execution_intents WHERE policy_id=? AND request_key=?',
                          (policy_id,request['request_key'])).fetchone()
            if row:
                item=json.loads(row[0])
                if item['request']!=request:raise ValueError('Idempotency key already belongs to different order facts')
                return item
            item=dict(id=str(uuid4()),policy_id=policy_id,request=request,state='DRAFT',
                      account_key=policy['account_key'],environment=policy['environment'],
                      strategy_key=policy['strategy_key'],strategy_source_hash=policy['strategy_source_hash'],
                      execution_enabled=False,created_at=datetime.now(timezone.utc).isoformat())
            c.execute('INSERT INTO mt5_execution_intents VALUES(?,?,?,?)',(item['id'],policy_id,request['request_key'],encoded(item)))
            return item

    def intents(self,policy_id):
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM mt5_execution_intents WHERE policy_id=? ORDER BY rowid',(policy_id,))]

    def record_reconciliation(self, intent_id, executions, open_positions, *,
                              broker_order_id, account_key, environment, complete,
                              observed_at_ms, use_attempt_receipt=False, _connection=None):
        """Persist backend broker evidence, not submission/attribution authority.

        The caller owns terminal locks and establishes snapshot completeness.
        A matching order alone does not prove this draft submitted it. Therefore
        observations never promote intent state, clear guards, or arm policies.
        There is deliberately no public endpoint accepting these facts.
        """
        from app.brokers.mt5_execution_reconciliation import reconcile_order

        self._manual_only()
        if type(use_attempt_receipt) is not bool or (use_attempt_receipt and broker_order_id is not None):
            raise ValueError('Receipt-bound reconciliation cannot accept an alternate order ticket')
        if type(observed_at_ms) is not int or observed_at_ms <= 0:
            raise ValueError('Invalid reconciliation observation timestamp')
        if broker_order_id is not None and (not isinstance(broker_order_id, str)
                or not broker_order_id.isascii() or not broker_order_id.isdigit()
                or not 1 <= len(broker_order_id) <= 20 or int(broker_order_id) <= 0):
            raise ValueError('Invalid broker order ticket')
        executions = list(executions)
        with (self.database.connect() if _connection is None else nullcontext(_connection)) as c:
            if _connection is None:c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_intents WHERE id=?', (intent_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution intent')
            intent = json.loads(row[0])
            attempt = None
            # Only a durable, broker-verified tightening may update the expected
            # protection for reconciliation. Original order facts stay immutable.
            protection_id = None
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_protection_attempts'").fetchone():
                protection = c.execute("SELECT document FROM mt5_protection_attempts WHERE state='VERIFIED' AND json_extract(document,'$.intent_id')=? ORDER BY rowid DESC LIMIT 1",(intent_id,)).fetchone()
                if protection:
                    verified=json.loads(protection[0]);old=intent['request']['stop'];new=verified['new_stop']
                    if (verified['target']!=intent['request']['target'] or
                            (new<old if intent['request']['side']=='buy' else new>old)):
                        raise ValueError('Recorded protection conflicts with original intent')
                    intent['request']['stop']=new
                    protection_id=verified['id']
            if use_attempt_receipt:
                attempt_row = c.execute('SELECT document FROM mt5_execution_attempts WHERE intent_id=?',
                                        (intent_id,)).fetchone()
                if not attempt_row:
                    raise ValueError('No durable submission attempt for this intent')
                attempt = json.loads(attempt_row[0])
                receipt = attempt['receipt']
                broker_order_id = receipt['broker_order_id'] if receipt else None
            decision = reconcile_order(intent, executions, open_positions,
                broker_order_id=broker_order_id, account_key=account_key,
                environment=environment, complete=complete)
            # Persist only allowlisted classifier output. Native metadata,
            # comments, account logins and provider errors never enter this log.
            record = dict(intent_id=intent_id, broker_order_id=broker_order_id,
                          observed_at_ms=observed_at_ms, decision=decision,
                          execution_count=len(executions), complete=complete is True,
                          execution_enabled=False, attribution_verified=False)
            if attempt is not None:
                record.update(attempt_id=attempt['id'], identity_basis='durable_attempt_receipt')
            if protection_id is not None:
                record['verified_protection_id']=protection_id
            identifier = sha256(encoded(record).encode()).hexdigest()
            record['id'] = identifier
            c.execute('INSERT OR IGNORE INTO mt5_execution_reconciliations VALUES(?,?,?)',
                      (identifier, intent_id, encoded(record)))
            if attempt is not None:
                previous = attempt.get('latest_reconciliation')
                # Retain late-arriving evidence in history without replacing a
                # newer recovery observation with an older snapshot.
                if previous is None or observed_at_ms > previous['observed_at_ms']:
                    attempt['latest_reconciliation'] = dict(id=identifier, observed_at_ms=observed_at_ms,
                                                             state=decision['state'])
                    c.execute('UPDATE mt5_execution_attempts SET document=? WHERE id=?',
                              (encoded(attempt), attempt['id']))
            return record

    def reconcile_attempt(self, intent_id, executions, open_positions, *,
                          account_key, environment, complete, observed_at_ms):
        """Use only the saved receipt's order identity; never infer a missing ID.

        Does not release an account guard or authorize resubmission. Broker
        snapshot collection/freshness and account-wide recovery remain required.
        """
        return self.record_reconciliation(intent_id, executions, open_positions,
            broker_order_id=None, account_key=account_key, environment=environment,
            complete=complete, observed_at_ms=observed_at_ms, use_attempt_receipt=True)

    def reconciliations(self, intent_id, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Reconciliation limit must be between 1 and 1000')
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute(
                'SELECT document FROM mt5_execution_reconciliations WHERE intent_id=? ORDER BY rowid DESC LIMIT ?',
                (intent_id, limit))]

    def reconcile_account_snapshot(self,policy_id,executions,open_positions,*,account_key,
                                   environment,currency,complete,observed_at_ms):
        """Atomically record one account observation, never release or arm it.

        Native collection must finish before entering this short write transaction.
        Receipt identities and owner fencing are rechecked from durable state.
        A failed classification/write rolls back every observation and latest pointer.
        """
        self._manual_only()
        if environment!='demo':raise ValueError('Recovery requires a demo account')
        executions=list(executions)
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');self._owns(c)
            raw=c.execute('SELECT document FROM mt5_execution_policies WHERE id=?',(policy_id,)).fetchone()
            policy=json.loads(raw[0])['policy'] if raw else {}
            if (policy.get('account_key'),policy.get('environment'),policy.get('currency'))!=(account_key,environment,currency):
                raise ValueError('Recovery account identity changed')
            rows=c.execute('''SELECT i.id FROM mt5_execution_intents i
                JOIN mt5_execution_attempts a ON a.intent_id=i.id
                JOIN mt5_execution_policies p ON p.id=i.policy_id
                WHERE json_extract(p.document,'$.policy.account_key')=? ORDER BY i.rowid''',(account_key,)).fetchall()
            return [self.record_reconciliation(row[0],executions,open_positions,
                broker_order_id=None,account_key=account_key,environment=environment,complete=complete,
                observed_at_ms=observed_at_ms,use_attempt_receipt=True,_connection=c) for row in rows]

    def begin_attempt(self, intent_id, *, guard_token):
        """Write-ahead uncertainty marker; grants NO permission to call MT5.

        Internal future gateway primitive. Authorization, fresh risk checks and
        terminal locks remain separate mandatory gates. Never resend an existing
        attempt, including one with no receipt after process death.
        """
        self._manual_only()
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_intents WHERE id=?', (intent_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution intent')
            intent = json.loads(row[0])
            if intent['environment'] != 'demo' or intent['state'] != 'DRAFT':
                raise ValueError('Attempt requires an unused demo draft')
            guard = c.execute('''SELECT 1 FROM mt5_execution_account_guards
                WHERE account_key=? AND owner=? AND token=? AND state='HELD' ''',
                (intent['account_key'], self.owner, guard_token)).fetchone()
            if not guard:
                raise ValueError('Attempt requires the current account guard')
            if c.execute('SELECT 1 FROM mt5_execution_readonly_guards WHERE token=?', (guard_token,)).fetchone():
                raise ValueError('Read-only diagnostics cannot begin submission attempts')
            policy = json.loads(c.execute('SELECT document FROM mt5_execution_policies WHERE id=?',
                                         (intent['policy_id'],)).fetchone()[0])
            if policy['status'] == 'EMERGENCY_STOP':
                raise ValueError('MT5 emergency stop is active')
            attempt = dict(id=str(uuid4()), intent_id=intent_id, account_key=intent['account_key'],
                           state='SUBMISSION_UNCERTAIN', receipt=None, execution_enabled=False,
                           created_at=datetime.now(timezone.utc).isoformat())
            c.execute('INSERT INTO mt5_execution_attempts VALUES(?,?,?,?,?)',
                      (attempt['id'], intent_id, intent['account_key'], None, encoded(attempt)))
            intent['state'] = 'SUBMISSION_UNCERTAIN'
            c.execute('UPDATE mt5_execution_intents SET document=? WHERE id=?', (encoded(intent), intent_id))
            c.execute("UPDATE mt5_execution_account_guards SET state='RECONCILIATION_REQUIRED' WHERE account_key=?",
                      (intent['account_key'],))
            return attempt

    def record_attempt_receipt(self, attempt_id, *, guard_token, retcode, broker_order_id=None):
        """Store native numeric evidence only, never infer fill/retry from codes."""
        self._manual_only()
        if type(retcode) is not int or not 0 <= retcode <= 2147483647:
            raise ValueError('Invalid broker return code')
        if broker_order_id is not None and (not isinstance(broker_order_id, str)
                or not broker_order_id.isascii() or not broker_order_id.isdigit()
                or not 1 <= len(broker_order_id) <= 20 or int(broker_order_id) <= 0):
            raise ValueError('Invalid broker order ticket')
        # Canonical numeric tickets cannot bypass account-wide uniqueness with zeros.
        broker_order_id = str(int(broker_order_id)) if broker_order_id else None
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_attempts WHERE id=?', (attempt_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution attempt')
            attempt = json.loads(row[0])
            if not c.execute('''SELECT 1 FROM mt5_execution_account_guards WHERE
                    account_key=? AND owner=? AND token=? AND state='RECONCILIATION_REQUIRED' ''',
                    (attempt['account_key'], self.owner, guard_token)).fetchone():
                raise ValueError('Receipt requires the original account guard')
            receipt = dict(retcode=retcode, broker_order_id=broker_order_id)
            if attempt['receipt'] is not None:
                if attempt['receipt'] != receipt:
                    raise ValueError('Broker receipt is immutable; reconciliation required')
                return attempt
            if broker_order_id and c.execute('''SELECT 1 FROM mt5_execution_attempts
                    WHERE account_key=? AND broker_order_id=? AND id<>?''',
                    (attempt['account_key'], broker_order_id, attempt_id)).fetchone():
                raise ValueError('Broker order is already linked to another attempt')
            attempt['receipt'] = receipt
            c.execute('UPDATE mt5_execution_attempts SET broker_order_id=?,document=? WHERE id=?',
                      (broker_order_id, encoded(attempt), attempt_id))
            return attempt

    def attempt(self, intent_id):
        with self.database.connect() as c:
            row = c.execute('SELECT document FROM mt5_execution_attempts WHERE intent_id=?', (intent_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def assess_risk(self, policy_id, facts, proposed, *, now_ms, session_key, max_session_trades=1):
        """Persist diagnostic acceptance/rejection, without arming or reserving.

        Only backend-collected, complete account facts belong here. This method
        is deliberately not a public API accepting user-supplied risk totals.
        """
        from app.brokers.mt5_execution_risk import AccountRiskFacts, ProposedRisk, assess

        self._manual_only()
        facts = AccountRiskFacts.model_validate(facts).model_dump()
        proposed = ProposedRisk.model_validate(proposed).model_dump()
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_policies WHERE id=?', (policy_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution policy')
            policy = json.loads(row[0])['policy']
            decision = assess(policy, facts, proposed, now_ms=now_ms,
                              session_key=session_key, max_session_trades=max_session_trades)
            record = dict(id=str(uuid4()), policy_id=policy_id, facts=facts, proposed=proposed,
                          decision=decision, max_session_trades=max_session_trades,
                          execution_enabled=False)
            c.execute('INSERT INTO mt5_execution_risk_assessments VALUES(?,?,?)',
                      (record['id'], policy_id, encoded(record)))
            return record

    def risk_assessments(self, policy_id, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('Risk assessment limit must be between 1 and 1000')
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute(
                'SELECT document FROM mt5_execution_risk_assessments WHERE policy_id=? ORDER BY rowid DESC LIMIT ?',
                (policy_id, limit))]

    @contextmanager
    def account_guard(self, policy_id, *, read_only=False):
        """Serialize future gateway operations across strategies and processes.

        This grants no trading permission. An interrupted/failed operation keeps
        the account blocked for explicit broker reconciliation, with no timeout
        takeover. No database transaction is held during broker IO.
        """
        self._manual_only()
        if type(read_only) is not bool:
            raise ValueError('Invalid account guard mode')
        token = str(uuid4())
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_policies WHERE id=?', (policy_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution policy')
            policy = json.loads(row[0])['policy']
            if policy['environment'] != 'demo':
                raise ValueError('MT5 execution authority requires a demo policy')
            account = policy['account_key']
            if c.execute('SELECT 1 FROM mt5_execution_account_guards WHERE account_key=?', (account,)).fetchone():
                raise ValueError('MT5 account busy or awaiting broker reconciliation')
            c.execute('INSERT INTO mt5_execution_account_guards VALUES(?,?,?,?,?)',
                      (account, self.owner, token, 'HELD', datetime.now(timezone.utc).isoformat()))
            if read_only:
                c.execute('INSERT INTO mt5_execution_readonly_guards VALUES(?,?,?,?,NULL)',
                          (token, account, 'ACTIVE', datetime.now(timezone.utc).isoformat()))
        try:
            yield token
        except BaseException:
            # Also retain authority after cancellation/KeyboardInterrupt. Never
            # record exception text, native replies or secrets.
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute("""UPDATE mt5_execution_account_guards SET state='RECONCILIATION_REQUIRED'
                             WHERE account_key=? AND owner=? AND token=?""", (account, self.owner, token))
                if read_only:
                    c.execute("UPDATE mt5_execution_readonly_guards SET state='FAILED' WHERE token=? AND state='ACTIVE'", (token,))
            raise
        else:
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                self._owns(c)
                deleted = c.execute("""DELETE FROM mt5_execution_account_guards
                    WHERE account_key=? AND owner=? AND token=? AND state='HELD'""",
                    (account, self.owner, token)).rowcount
                if deleted != 1:
                    retained = c.execute('''SELECT 1 FROM mt5_execution_account_guards
                        WHERE account_key=? AND owner=? AND token=? AND state='RECONCILIATION_REQUIRED' ''',
                        (account, self.owner, token)).fetchone()
                    if not retained:
                        raise ValueError('MT5 account authority changed; broker reconciliation required')
                elif read_only:
                    c.execute('DELETE FROM mt5_execution_readonly_guards WHERE token=?', (token,))

    def recover_failed_diagnostic(self, policy_id):
        """Release only a finished read-only failure, never broker uncertainty.

        Legacy/untyped guards, active or killed diagnostics, and any account with
        attempts remain blocked. This grants no execution permission and performs
        no broker operations. Recovery evidence is retained for audit.
        """
        self._manual_only()
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._owns(c)
            row = c.execute('SELECT document FROM mt5_execution_policies WHERE id=?', (policy_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution policy')
            policy = json.loads(row[0])['policy']
            if policy['environment'] != 'demo':
                raise ValueError('Diagnostic recovery requires a demo policy')
            account = policy['account_key']
            guard = c.execute('SELECT token,state FROM mt5_execution_account_guards WHERE account_key=?', (account,)).fetchone()
            if not guard:
                return dict(status='already_idle', execution_enabled=False)
            evidence = c.execute('SELECT state FROM mt5_execution_readonly_guards WHERE token=? AND account_key=?',
                                 (guard['token'], account)).fetchone()
            if (guard['state'] != 'RECONCILIATION_REQUIRED' or not evidence or evidence['state'] != 'FAILED'
                    or c.execute('SELECT 1 FROM mt5_execution_attempts WHERE account_key=?', (account,)).fetchone()):
                raise ValueError('Broker reconciliation required; no recoverable read-only failure')
            c.execute("UPDATE mt5_execution_readonly_guards SET state='RECOVERED',recovered_at=? WHERE token=?",
                      (datetime.now(timezone.utc).isoformat(), guard['token']))
            c.execute('DELETE FROM mt5_execution_account_guards WHERE account_key=? AND token=?', (account, guard['token']))
            return dict(status='diagnostic_recovered', execution_enabled=False)

    def account_guard_status(self, policy_id):
        with self.database.connect() as c:
            row = c.execute('SELECT document FROM mt5_execution_policies WHERE id=?', (policy_id,)).fetchone()
            if not row:
                raise ValueError('Unknown MT5 execution policy')
            account = json.loads(row[0])['policy']['account_key']
            guard = c.execute('SELECT state,created_at FROM mt5_execution_account_guards WHERE account_key=?',
                              (account,)).fetchone()
            return dict(state=guard['state'] if guard else 'IDLE',
                        since=guard['created_at'] if guard else None, execution_enabled=False)

    def emergency_stop(self):
        # Disabling remains permitted even for a superseded process.
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in c.execute('SELECT id,document FROM mt5_execution_policies').fetchall():
                item=json.loads(row['document']);item.update(enabled=False,reconciled=False,status='EMERGENCY_STOP')
                c.execute('UPDATE mt5_execution_policies SET document=? WHERE id=?',(encoded(item),row['id']))
        return {'status':'disabled','positions_closed':False}

    def authorize_submission(self,*args,**kwargs):
        raise ValueError('MT5 submission is disabled: risk gateway and broker reconciliation acceptance are incomplete')
