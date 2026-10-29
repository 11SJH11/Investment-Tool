"""DEMO native submission boundary, separate from both read-only bridges.

No HTTP endpoint or terminal initialization. The caller owns terminal lifetime.
The default authorization gate denies every call. A future worker must supply an
independently verified, authenticated deployment authority and coexistence lease;
passing broker diagnostics alone must never be used as that authority.
"""
from copy import deepcopy
from decimal import Decimal
import json
from app.forward.deployments import digest,encoded
from app.brokers.mt5_order_preparation import prepare
from app.brokers.mt5_recovery_snapshot import collect
from app.brokers.mt5_risk_observation import observe, gross_exposure
from app.brokers.mt5_execution_reconciliation import reconcile_order


def deny_authority(**kwargs):
    raise ValueError('DEMO submission requires accepted deployment authority')


class DemoSubmission:
    def __init__(self, ledger, *, require_authority=deny_authority):
        self.ledger = ledger
        self.require_authority = require_authority

    def recover_protection(self, adapter, policy_id, protection_id):
        """Observe an uncertain SL change without resending or granting authority.

        Only an open, receipt-owned position at exactly the requested SL/TP can
        resolve uncertainty. A closed position cannot prove which stop applied.
        Account-wide recovery remains a separate step and never re-arms trading.
        """
        ledger = self.ledger
        ledger._manual_only()
        with ledger.database.connect() as c:
            ledger._owns(c)
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_protection_attempts'").fetchone():
                raise ValueError('Unknown protection attempt')
            row = c.execute('SELECT document FROM mt5_protection_attempts WHERE id=?',
                            (protection_id,)).fetchone()
        if not row:
            raise ValueError('Unknown protection attempt')
        record = json.loads(row[0])
        intent = next((i for i in ledger.intents(policy_id) if i['id'] == record['intent_id']), None)
        if not intent:
            raise ValueError('Protection attempt belongs to another policy')
        if record['state'] == 'VERIFIED':
            return record
        attempt = ledger.attempt(intent['id'])
        receipt = (attempt or {}).get('receipt') or {}
        if not receipt.get('broker_order_id'):
            raise ValueError('Protection recovery requires a durable entry receipt')
        original = Decimal(str(intent['request']['stop']))
        desired = Decimal(str(record['new_stop']))
        if (not desired.is_finite() or desired <= 0
                or record['target'] != intent['request']['target']
                or (desired < original if intent['request']['side'] == 'buy' else desired > original)):
            raise ValueError('Protection attempt conflicts with immutable intent')
        snapshot = collect(adapter)
        comparison = deepcopy(intent)
        comparison['request']['stop'] = record['new_stop']
        evidence = reconcile_order(comparison, snapshot['executions'], snapshot['open_positions'],
            broker_order_id=receipt['broker_order_id'], account_key=snapshot['account_key'],
            environment=snapshot['environment'], complete=snapshot['complete'])
        if (evidence['state'] not in {'FILLED_PROTECTED', 'PARTIAL_PROTECTED'}
                or evidence.get('position_id') != record['position_id']
                or snapshot['pending_order_ids']):
            return record
        account, account_key = adapter._account()
        if (adapter.environment != 'demo' or snapshot['environment'] != 'demo'
                or account.trade_mode != adapter._module.ACCOUNT_TRADE_MODE_DEMO
                or account_key != intent['account_key'] or adapter.account_key != account_key
                or account.currency != snapshot['currency']):
            raise ValueError('Protection recovery requires the original DEMO account')
        with ledger.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            ledger._owns(c)
            if not 0 <= int(adapter._clock()*1000)-snapshot['observed_at_ms'] <= 5000:
                raise ValueError('Protection recovery evidence expired')
            current = c.execute('SELECT document FROM mt5_protection_attempts WHERE id=?',
                                (protection_id,)).fetchone()
            if not current or current[0] != row[0]:
                raise ValueError('Protection attempt changed during recovery')
            record.update(state='VERIFIED', recovered_at_ms=snapshot['observed_at_ms'],
                          verification_basis='receipt_owned_complete_broker_snapshot')
            c.execute('UPDATE mt5_protection_attempts SET state=?,document=? WHERE id=?',
                      (record['state'], encoded(record), protection_id))
        return record

    def recover(self,adapter,policy_id):
        """Release only positively reconciled account uncertainty; never re-arm.

        No order ticket means no automatic recovery. A timed-out send can still
        arrive at the broker later. External pending orders also block this first
        integration, without cancelling or claiming ownership of them.
        """
        ledger=self.ledger;ledger._manual_only()
        snapshot=collect(adapter)
        records=ledger.reconcile_account_snapshot(policy_id,snapshot['executions'],snapshot['open_positions'],
            account_key=snapshot['account_key'],environment=snapshot['environment'],currency=snapshot['currency'],
            complete=snapshot['complete'],observed_at_ms=snapshot['observed_at_ms'])
        safe={'FILLED_PROTECTED','PARTIAL_PROTECTED','CLOSED','PARTIAL_CLOSED'}
        if (not snapshot['complete'] or snapshot['pending_order_ids']
                or any(r['decision']['state'] not in safe for r in records)):
            return dict(status='RECONCILIATION_REQUIRED',account_released=False,observations=records)
        with ledger.database.connect() as c:
            c.execute('BEGIN IMMEDIATE');ledger._owns(c)
            if not 0<=int(adapter._clock()*1000)-snapshot['observed_at_ms']<=5000:
                raise ValueError('Recovery evidence expired before commit')
            count=c.execute('SELECT COUNT(*) FROM mt5_execution_attempts WHERE account_key=?',(snapshot['account_key'],)).fetchone()[0]
            if count!=len(records):raise ValueError('Attempt set changed during recovery')
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_protection_attempts'").fetchone():
                unresolved=c.execute("SELECT 1 FROM mt5_protection_attempts WHERE account_key=? AND state!='VERIFIED' LIMIT 1",(snapshot['account_key'],)).fetchone()
                if unresolved:return dict(status='PROTECTION_RECONCILIATION_REQUIRED',account_released=False,observations=records)
            c.execute("DELETE FROM mt5_execution_account_guards WHERE account_key=? AND state='RECONCILIATION_REQUIRED'",(snapshot['account_key'],))
            still_held=c.execute('SELECT 1 FROM mt5_execution_account_guards WHERE account_key=?',(snapshot['account_key'],)).fetchone()
        return dict(status='ACCOUNT_BUSY' if still_held else 'RECONCILED_NOT_ARMED',account_released=not bool(still_held),observations=records,execution_enabled=False)

    def tighten_stop(self,adapter,policy_id,intent_id,*,decision_id,new_stop):
        """Receipt-owned, improving SL only. TP is preserved; no closes or cancels.

        Worker authority must verify the persisted canonical management decision.
        Repeated/uncertain modifications are never blindly resent.
        """
        ledger=self.ledger;ledger._manual_only()
        if self.require_authority(policy_id=policy_id,intent_id=intent_id,action='manage',decision_id=decision_id,new_stop=new_stop) is not True:
            raise ValueError('Verified management authority required')
        if not isinstance(decision_id,str) or not 1<=len(decision_id)<=128:
            raise ValueError('Invalid management decision')
        stop=Decimal(str(new_stop))
        if not stop.is_finite() or stop<=0:raise ValueError('Invalid stop')
        intent=next((i for i in ledger.intents(policy_id) if i['id']==intent_id),None)
        attempt=ledger.attempt(intent_id)
        if not intent or not attempt or not (attempt.get('receipt') or {}).get('broker_order_id'):
            raise ValueError('A durable broker receipt is required for management')
        key=digest(dict(intent_id=intent_id,decision_id=decision_id))
        with ledger.database.connect() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='mt5_protection_attempts'").fetchone():
                old=c.execute('SELECT document FROM mt5_protection_attempts WHERE id=?',(key,)).fetchone()
                if old:
                    value=json.loads(old[0])
                    if value['new_stop']!=float(stop):raise ValueError('Management decision is immutable')
                    return value
        with ledger.account_guard(policy_id) as token:
            snapshot=collect(adapter)
            request=intent['request']
            # Derive position identity only from this receipt's entry fills.
            ids={e.position_id for e in snapshot['executions'] if e.role=='entry' and e.order_id==attempt['receipt']['broker_order_id']}
            if len(ids)!=1:raise ValueError('Position ownership is unresolved')
            position_id=next(iter(ids));position=snapshot['open_positions'].get(position_id)
            if not position:raise ValueError('Owned position is not open')
            current=Decimal(str(position['stop']))
            original=Decimal(str(request['stop']))
            long=request['side']=='buy'
            if (not original<=current<=stop if long else not stop<=current<=original):
                raise ValueError('Stop must never loosen initial or current protection')
            comparison=deepcopy(intent);comparison['request']['stop']=position['stop']
            evidence=reconcile_order(comparison,snapshot['executions'],snapshot['open_positions'],
                broker_order_id=attempt['receipt']['broker_order_id'],account_key=snapshot['account_key'],
                environment=snapshot['environment'],complete=snapshot['complete'])
            if evidence['state'] not in {'FILLED_PROTECTED','PARTIAL_PROTECTED'}:
                raise ValueError('Position ownership or protection is unverified')
            module=adapter._module
            candidates=[p for p in module.positions_get() if str(p.identifier)==position_id]
            if len(candidates)!=1:raise ValueError('Position ticket changed')
            native=candidates[0]
            if (native.symbol!=request['symbol'] or native.volume!=position['quantity_lots']
                    or native.sl!=position['stop'] or native.tp!=request['target']
                    or native.type!=(module.ORDER_TYPE_BUY if long else module.ORDER_TYPE_SELL)):
                raise ValueError('Position changed before management')
            info=module.symbol_info(native.symbol);quote=module.symbol_info_tick(native.symbol)
            if info is None or quote is None or not 0<=int(adapter._clock()*1000)-quote.time_msc<=5000:
                raise ValueError('Management quote unavailable or stale')
            tick=Decimal(str(info.trade_tick_size));point=Decimal(str(info.point))
            if tick<=0 or point<=0 or stop%tick:raise ValueError('Stop tick alignment')
            minimum=max(info.trade_stops_level,info.trade_freeze_level)
            if minimum<0:raise ValueError('Invalid broker stop/freeze level')
            reference=Decimal(str(quote.bid if long else quote.ask))
            gap=reference-stop if long else stop-reference
            if gap<=0 or gap<Decimal(str(minimum))*point:raise ValueError('Stop violates broker distance/freeze level')
            account,account_key=adapter._account()
            if adapter.environment!='demo' or account.trade_mode!=module.ACCOUNT_TRADE_MODE_DEMO or account_key!=intent['account_key']:
                raise ValueError('Management requires the original DEMO account')
            if self.require_authority(policy_id=policy_id,intent_id=intent_id,action='manage',decision_id=decision_id,new_stop=new_stop) is not True:
                raise ValueError('Management authority revoked')
            record=dict(id=key,intent_id=intent_id,decision_id=decision_id,position_id=position_id,
                new_stop=float(stop),target=request['target'],state='SUBMISSION_UNCERTAIN',broker_retcode=None)
            with ledger.database.connect() as c:
                c.execute('BEGIN IMMEDIATE');ledger._owns(c)
                c.execute('CREATE TABLE IF NOT EXISTS mt5_protection_attempts(id TEXT PRIMARY KEY,account_key TEXT NOT NULL,state TEXT NOT NULL,document TEXT NOT NULL)')
                c.execute('INSERT INTO mt5_protection_attempts VALUES(?,?,?,?)',(key,intent['account_key'],record['state'],encoded(record)))
                c.execute("UPDATE mt5_execution_account_guards SET state='RECONCILIATION_REQUIRED' WHERE account_key=? AND token=?",(intent['account_key'],token))
            try:
                response=module.order_send(dict(action=module.TRADE_ACTION_SLTP,position=native.ticket,
                    symbol=native.symbol,sl=float(stop),tp=request['target']))
                if response is not None and type(response.retcode) is int:record['broker_retcode']=response.retcode
                after=module.positions_get()
                account,after_key=adapter._account()
                matching=[p for p in after if str(p.identifier)==position_id] if after is not None else []
                if (after_key==intent['account_key'] and account.trade_mode==module.ACCOUNT_TRADE_MODE_DEMO
                        and adapter.environment=='demo' and len(matching)==1
                        and matching[0].ticket==native.ticket and matching[0].symbol==native.symbol
                        and matching[0].volume==native.volume and matching[0].sl==float(stop)
                        and matching[0].tp==request['target']):record['state']='VERIFIED'
            except Exception:pass  # Uncertain remains blocked; no secret/native text.
            with ledger.database.connect() as c:
                c.execute('BEGIN IMMEDIATE');ledger._owns(c)
                c.execute('UPDATE mt5_protection_attempts SET state=?,document=? WHERE id=?',(record['state'],encoded(record),key))
                if record['state']=='VERIFIED':
                    c.execute("UPDATE mt5_execution_account_guards SET state='HELD' WHERE account_key=? AND token=?",(intent['account_key'],token))
            return record

    def submit(self, adapter, policy_id, intent_id, *, risk_percent, session_key,
               magic, deviation_points, max_session_trades=1):
        """One guarded native attempt; never retries, infers ownership or clears guards.

        ``require_authority`` is an internal worker boundary, not user supplied
        request data. It must hold verified timestamp/coexistence authority for the
        full call and reject expired, paused, stopped or source-mismatched runs.
        It is checked again immediately before persisting the attempt.
        """
        ledger = self.ledger
        ledger._manual_only()
        if self.require_authority(policy_id=policy_id, intent_id=intent_id, action='entry') is not True:
            raise ValueError('Verified deployment authority required')
        policy = next((p['policy'] for p in ledger.policies() if p['id']==policy_id), None)
        intent = next((i for i in ledger.intents(policy_id) if i['id']==intent_id), None)
        if not policy or not intent or policy['environment']!='demo' or intent['state']!='DRAFT':
            raise ValueError('Submission requires an unused verified DEMO intent')
        if not isinstance(session_key,str) or not 1<=len(session_key)<=128:
            raise ValueError('Invalid session identity')
        if ledger.attempt(intent_id):
            raise ValueError('Intent already attempted; reconcile instead of retrying')
        with ledger.account_guard(policy_id) as token:
            account,key=adapter._account()
            if (adapter.environment!='demo' or account.trade_mode!=adapter._module.ACCOUNT_TRADE_MODE_DEMO
                    or key!=policy['account_key'] or adapter.account_key!=key or account.currency!=policy['currency']):
                raise ValueError('Native account differs from DEMO policy')
            draft=intent['request']
            checked=prepare(adapter,dict(symbol=draft['symbol'],side=draft['side'],
                stop=draft['stop'],target=draft['target'],risk_percent=risk_percent),
                intent_id=intent_id,magic=magic,deviation_points=deviation_points)
            if checked['status']!='broker_check_passed':
                return dict(status='BROKER_CHECK_REJECTED',orders_sent=False)
            sizing=checked['preflight']['sizing']
            if any(sizing[k]!=draft[k] for k in ('symbol','side','entry','stop','quantity_lots')):
                raise ValueError('Fresh sizing differs from immutable order intent')
            snapshot=collect(adapter)
            if snapshot['account_key']!=key or snapshot['environment']!='demo' or snapshot['currency']!=policy['currency']:
                raise ValueError('Recovery snapshot account mismatch')
            records=ledger.reconcile_account_snapshot(policy_id,snapshot['executions'],snapshot['open_positions'],
                account_key=key,environment='demo',currency=policy['currency'],complete=snapshot['complete'],
                observed_at_ms=snapshot['observed_at_ms'])
            safe={'FILLED_PROTECTED','PARTIAL_PROTECTED','CLOSED','PARTIAL_CLOSED'}
            unresolved=sum(r['decision']['state'] not in safe for r in records)
            # Session identity must come from the verified worker authority.
            # Legacy attempts without attribution remain conservative blockers.
            entries=ledger.session_attempt_count(policy_id,session_key)
            facts=observe(adapter,strategy_key=policy['strategy_key'],session_key=session_key,
                session_entries=entries,unresolved_submissions=unresolved)
            facts['reconciled']=snapshot['complete'] is True and unresolved==0
            now_ms=int(adapter._clock()*1000)
            if not 0<=now_ms-snapshot['observed_at_ms']<=5000:
                raise ValueError('Recovery evidence expired')
            proposed=dict(symbol=draft['symbol'],estimated_stop_risk=sizing['actual_estimated_risk'],
                estimated_margin=sizing['estimated_margin'],gross_exposure=gross_exposure(adapter._module,
                    draft['symbol'],sizing['quantity_lots'],sizing['entry'],policy['currency']))
            assessment=ledger.assess_risk(policy_id,facts,proposed,now_ms=now_ms,
                session_key=session_key,max_session_trades=max_session_trades)
            if not assessment['decision']['allowed']:
                return dict(status='RISK_REJECTED',reasons=assessment['decision']['reasons'],orders_sent=False)
            # Recheck prices, permissions, margin, identity and the broker check.
            # Do not change an immutable intent to chase a moved quote.
            fresh=prepare(adapter,dict(symbol=draft['symbol'],side=draft['side'],stop=draft['stop'],
                target=draft['target'],risk_percent=risk_percent),intent_id=intent_id,magic=magic,
                deviation_points=deviation_points)
            if (fresh['status']!='broker_check_passed' or fresh['request']!=checked['request']
                    or any(fresh['preflight']['sizing'].get(k)!=v for k,v in sizing.items() if k!='observed_at')
                    or not 0<=int(adapter._clock()*1000)-facts['observed_at_ms']<=5000):
                raise ValueError('Prepared request or account risk changed before submission')
            quote=adapter._module.symbol_info_tick(draft['symbol'])
            if (quote is None or quote.bid!=fresh['preflight']['bid'] or quote.ask!=fresh['preflight']['ask']
                    or not 0<=int(adapter._clock()*1000)-quote.time_msc<=5000):
                raise ValueError('Executable quote changed before submission')
            if self.require_authority(policy_id=policy_id,intent_id=intent_id,action='entry') is not True:
                raise ValueError('Deployment authority was revoked')
            attempt=ledger.begin_attempt(intent_id,guard_token=token,
                session_key=session_key,max_session_trades=max_session_trades)
            # From this point every outcome remains durably blocked until receipt-
            # bound recovery. Even a timeout can mean the broker accepted it.
            try:
                account,final_key=adapter._account()
                if (final_key!=key or adapter.account_key!=key or adapter.environment!='demo'
                        or account.trade_mode!=adapter._module.ACCOUNT_TRADE_MODE_DEMO):
                    return dict(status='IDENTITY_CHANGED_RECONCILIATION_REQUIRED',attempt_id=attempt['id'],orders_sent=False)
                result=adapter._module.order_send(dict(fresh['request']))
                if result is None or type(result.retcode) is not int:
                    return dict(status='SUBMISSION_UNCERTAIN',attempt_id=attempt['id'],orders_sent=None)
                ticket=result.order
                if type(ticket) is not int or ticket<0:
                    return dict(status='SUBMISSION_UNCERTAIN',attempt_id=attempt['id'],orders_sent=None)
            except Exception:
                # No terminal exception string, credential or native comment escapes.
                return dict(status='SUBMISSION_UNCERTAIN',attempt_id=attempt['id'],orders_sent=None)
            ledger.record_attempt_receipt(attempt['id'],guard_token=token,retcode=result.retcode,
                broker_order_id=str(ticket) if ticket else None)
            return dict(status='RECEIPT_RECORDED_RECONCILIATION_REQUIRED',attempt_id=attempt['id'],
                broker_retcode=result.retcode,broker_order_id=str(ticket) if ticket else None,
                orders_sent=True,position_verified=False,protection_verified=False)
