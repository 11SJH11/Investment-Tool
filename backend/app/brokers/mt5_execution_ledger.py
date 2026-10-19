"""Durable MT5 execution groundwork; no native submission or arming capability.

Policies and drafts are inspectable but cannot authorize a broker call. Future
gateways must establish reconciliation and risk checks before adding that path.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

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
            c.execute('BEGIN IMMEDIATE')
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
