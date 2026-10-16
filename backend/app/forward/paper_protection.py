"""Broker-held closing protection with explicitly disclosed post-fill gaps.

Partial entries are cancelled before protecting the final reconciled quantity.
Earlier exits wait for confirmed MOC cancellation. No retry of unknown submissions,
no simulated fills, and no timer substitution for broker-held protection.
"""
from .bars import stamp
from .paper_gateway import TERMINAL,number
from datetime import timedelta

ACK='Paper only: I accept the post-fill and cancel/replace protection gaps'


class PaperProtection:
    def __init__(self,gateway):self.gateway=gateway

    def _state(self,identifier,status,**details):
        item=self.gateway.get(identifier)
        item['close_protection']={'status':status,'observed_at':stamp(self.gateway.clock()).isoformat(),**details}
        with self.gateway.database.connect() as c:self.gateway._save(c,item)
        return item['close_protection']

    def request_exit(self,identifier,reason):
        with self.gateway.lock:
            item=self.gateway.get(identifier)
            if not item.get('exit_request'):
                item['exit_request']={'requested_at':stamp(self.gateway.clock()).isoformat(),'reason':reason}
                with self.gateway.database.connect() as c:self.gateway._save(c,item)
            return self.maintain(identifier)

    def maintain(self,identifier):
        with self.gateway.lock:
            try:
                item=self.gateway.reconcile(identifier,allow_risk_breach=True)
                intents=self.gateway.intents(identifier)
                active=[i for i in intents if i['state'].lower() not in TERMINAL]
                entries=[i for i in active if i['action']=='entry']
                closes=[i for i in active if i.get('purpose')=='session_close']
                exits=[i for i in active if i['action']=='exit' and i.get('purpose')!='session_close']
                quantity=abs(number(item['position_qty']))
                if entries:
                    if quantity or item.get('exit_request'):
                        self.gateway.cancel_intents(identifier,{i['client_order_id'] for i in entries})
                        # Never treat cancellation acknowledgement as a final quantity.
                        remaining=[i for i in self.gateway.intents(identifier) if i['action']=='entry' and i['state'].lower() not in TERMINAL]
                        if remaining:return self._state(identifier,'ENTRY_CANCEL_PENDING',protected=False)
                        return self.maintain(identifier)
                    return self._state(identifier,'ENTRY_FILL_PENDING',protected=False)
                if exits:
                    return self._state(identifier,'EXIT_PENDING',protected=False)
                if not quantity:
                    if closes:
                        self.gateway.cancel_intents(identifier,{i['client_order_id'] for i in closes})
                        remaining=[i for i in self.gateway.intents(identifier) if i.get('purpose')=='session_close' and i['state'].lower() not in TERMINAL]
                        if remaining:return self._state(identifier,'CLOSE_CANCEL_PENDING',protected=False)
                    item=self.gateway.get(identifier);item.pop('exit_request',None)
                    with self.gateway.database.connect() as c:self.gateway._save(c,item)
                    return self._state(identifier,'FLAT',protected=False)
                if item.get('exit_request'):
                    if closes:
                        clock=self.gateway.client.clock()
                        if not clock.get('is_open') or not clock.get('next_close') or stamp(self.gateway.clock())>=stamp(clock['next_close'])-timedelta(minutes=10):
                            verified=self.gateway.protect_close(identifier)
                            return self._state(identifier,'EXIT_DEFERRED_TO_AUCTION',protected=True,client_order_id=verified['client_order_id'])
                        self.gateway.cancel_intents(identifier,{i['client_order_id'] for i in closes})
                        remaining=[i for i in self.gateway.intents(identifier) if i.get('purpose')=='session_close' and i['state'].lower() not in TERMINAL]
                        if remaining:return self._state(identifier,'CLOSE_CANCEL_PENDING',protected=False)
                    intent=self.gateway.exit_reconciled(identifier)
                    return self._state(identifier,'EXIT_PENDING' if intent else 'FLAT',protected=False,
                                       client_order_id=intent['client_order_id'] if intent else None)
                previous=item.get('close_protection',{}).get('client_order_id')
                previous_intent=next((i for i in intents if i['client_order_id']==previous),None)
                if previous_intent and previous_intent['state'].lower() in TERMINAL:
                    raise ValueError('Closing protection ended while broker position remains open')
                last_entry=max((n for n,i in enumerate(intents) if i['action']=='entry'),default=-1)
                if any(i.get('purpose')=='session_close' and i['state'].lower() in TERMINAL for i in intents[last_entry+1:]):
                    raise ValueError('Closing protection ended; no automatic replacement')
                intent=self.gateway.protect_close(identifier)
                # Bind the submitted ID before lookup; restart must reconcile it.
                self._state(identifier,'PROTECTION_CONFIRMATION_PENDING',protected=False,client_order_id=intent['client_order_id'])
                self.gateway.reconcile(identifier,allow_risk_breach=True)
                confirmed=next(i for i in self.gateway.intents(identifier) if i['client_order_id']==intent['client_order_id'])
                if confirmed['state'].lower() in TERMINAL:
                    if number(self.gateway.get(identifier)['position_qty'])==0:return self.maintain(identifier)
                    raise ValueError('Closing protection was rejected or ended')
                verified=self.gateway.protect_close(identifier)
                return self._state(identifier,'PROTECTED',protected=True,client_order_id=verified['client_order_id'])
            except Exception:
                self.gateway.disarm(identifier,'close_protection_requires_review')
                self._state(identifier,'REVIEW_REQUIRED',protected=False)
                raise
