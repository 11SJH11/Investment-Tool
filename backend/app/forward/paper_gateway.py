"""Durable paper intent/risk boundary. Submission is never evidence of a fill."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal, ROUND_DOWN
import json
from threading import RLock
from uuid import uuid4
from zoneinfo import ZoneInfo
from pydantic import BaseModel,ConfigDict,Field
from .bars import stamp
from .deployments import Deployments,encoded,digest

B_KEY='vwap_d6_mss15_no_opp_fvg15_research_v1'
TERMINAL={'filled','canceled','expired','rejected'}
KNOWN=TERMINAL|{'new','accepted','pending_new','partially_filled','pending_cancel','accepted_for_bidding','done_for_day'}

class PaperRisk(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    fixed_notional:float=Field(gt=0,le=1_000_000)
    max_equity_fraction:float=Field(default=.1,gt=0,le=1)
    max_daily_loss_percent:float=Field(default=2,gt=0,le=10)

def number(value):
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Non-finite broker fact')
    return result


class PaperGateway:
    def __init__(self,database,client,clock=lambda:datetime.now(timezone.utc)):
        self.database=database;self.client=client;self.clock=clock;self.lock=RLock()
        self.owner=str(uuid4())
        with database.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS forward_paper_owner(id INTEGER PRIMARY KEY CHECK(id=1),owner TEXT NOT NULL)')
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO forward_paper_owner VALUES (1,?) ON CONFLICT(id) DO UPDATE SET owner=excluded.owner',(self.owner,))
            c.execute('''CREATE TABLE IF NOT EXISTS forward_paper(
                id TEXT PRIMARY KEY,experiment_id TEXT NOT NULL UNIQUE,document TEXT NOT NULL,
                FOREIGN KEY(experiment_id) REFERENCES forward_experiments(id))''')
            c.execute('''CREATE TABLE IF NOT EXISTS forward_paper_intents(
                client_order_id TEXT PRIMARY KEY,deployment_id TEXT NOT NULL,document TEXT NOT NULL,
                FOREIGN KEY(deployment_id) REFERENCES forward_paper(id))''')
            # Restart always requires reconciliation and a fresh explicit arm.
            for row in c.execute('SELECT id,document FROM forward_paper'):
                item=json.loads(row[1]);item.update(armed=False,reconciled=False,last_error='restart_reconciliation_required')
                c.execute('UPDATE forward_paper SET document=? WHERE id=?',(encoded(item),row[0]))

    def _owns(self,c=None):
        if c is None:
            with self.database.connect() as connection:return self._owns(connection)
        row=c.execute('SELECT owner FROM forward_paper_owner WHERE id=1').fetchone()
        if not row or row[0]!=self.owner:raise ValueError('Paper gateway superseded by a newer process')

    def _save(self,c,item):
        self._owns(c)
        c.execute('UPDATE forward_paper SET document=? WHERE id=?',(encoded(item),item['id']))
    def get(self,identifier):
        with self.database.connect() as c:
            row=c.execute('SELECT document FROM forward_paper WHERE id=?',(identifier,)).fetchone()
            if not row:raise ValueError('Unknown paper deployment')
            return json.loads(row[0])
    def intents(self,identifier):
        with self.database.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT document FROM forward_paper_intents WHERE deployment_id=? ORDER BY rowid',(identifier,))]

    def create(self,experiment,risk):
        risk=PaperRisk.model_validate(risk).model_dump()
        rows=Deployments(self.database).list(experiment)
        source=next((r for r in rows if r['definition']['strategy_key']==B_KEY),None)
        if not source:raise ValueError('A frozen B shadow definition is required')
        with self.lock,self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT document FROM forward_paper WHERE experiment_id=?',(experiment,)).fetchone()
            if previous:
                item=json.loads(previous[0])
                if item['risk']!=risk:raise ValueError('Paper risk is immutable; create a new experiment')
                return item
            item=dict(id=str(uuid4()),experiment_id=experiment,mode='ALPACA_PAPER',symbol='QQQ',
                      strategy_key=B_KEY,definition=source['definition'],definition_sha256=source['definition_sha256'],
                      risk=risk,armed=False,reconciled=False,account_id=None,position_qty='0',last_error=None)
            c.execute('INSERT INTO forward_paper VALUES (?,?,?)',(item['id'],experiment,encoded(item)))
            return item

    def disarm(self,identifier,reason='user_disarmed'):
        with self.lock,self.database.connect() as c:
            item=self.get(identifier);item.update(armed=False,last_error=reason);self._save(c,item)
            return item

    def reconcile(self,identifier,*,allow_risk_breach=False):
        with self.lock:
            self._owns()
            item=self.get(identifier)
            try:
                account=self.client.account();positions=self.client.positions();open_orders=self.client.open_orders()
                if account.get('status')!='ACTIVE' or account.get('trading_blocked') or account.get('account_blocked'):
                    raise ValueError('Paper account is blocked or inactive')
                if not account.get('id') or item['account_id'] not in (None,account['id']):raise ValueError('Paper account identity changed')
                if any(p.get('symbol')!='QQQ' for p in positions) or len(positions)>1:raise ValueError('Dedicated paper account has unexpected positions')
                intents=self.intents(identifier);known={i['client_order_id'] for i in intents}
                if any(o.get('client_order_id') not in known for o in open_orders):raise ValueError('Unknown paper order requires review')
                updates=[];expected=Decimal(0)
                for intent in intents:
                    if intent['state']=='CREATED':continue
                    order=self.client.find(intent['client_order_id'])
                    if order is None:raise ValueError('Submitted paper intent cannot be reconciled; no resubmission')
                    request=intent['order'];filled=number(order.get('filled_qty',0))
                    if (order.get('client_order_id')!=intent['client_order_id'] or order.get('symbol')!='QQQ' or
                        order.get('side')!=request['side'] or order.get('status') not in KNOWN or
                        order.get('time_in_force')!=request['time_in_force'] or order.get('type')!=request['type'] or
                        (intent.get('broker',{}).get('id') and intent['broker']['id']!=order.get('id')) or
                        number(order.get('qty'))!=number(request['qty']) or not 0<=filled<=number(request['qty']) or
                        filled<number(intent.get('broker',{}).get('filled_qty',0))):
                        raise ValueError('Paper order facts do not match durable intent')
                    if filled and number(order.get('filled_avg_price'))<=0:raise ValueError('Missing broker fill price')
                    expected+=filled*(1 if request['side']=='buy' else -1)
                    # Persist only required broker facts, not an arbitrary provider response.
                    facts={k:order.get(k) for k in ('id','client_order_id','symbol','side','qty','filled_qty','filled_avg_price','status','submitted_at','filled_at','canceled_at')}
                    if filled and not intent.get('first_fill_observed_at'):
                        intent['first_fill_observed_at']=stamp(self.clock()).isoformat()
                    intent.update(state=str(order['status']).upper(),broker=facts);updates.append(intent)
                actual=number(positions[0]['qty']) if positions else Decimal(0)
                if actual!=expected:raise ValueError('Broker position differs from reconciled Ledger fills')
                equity=number(account['equity'])
                if equity<=0:raise ValueError('Paper equity is invalid')
                day=stamp(self.clock()).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                if item.get('equity_day')!=day:item.update(equity_day=day,opening_equity=str(equity))
                loss_breached=equity<number(item['opening_equity'])*(1-number(item['risk']['max_daily_loss_percent'])/100)
                if loss_breached and not allow_risk_breach:
                    raise ValueError('Paper daily loss limit reached')
                item.update(account_id=account['id'],position_qty=str(actual),account_equity=str(equity),
                            position=positions[0] if positions else None,reconciled=True,
                            reconciled_at=stamp(self.clock()).isoformat(),last_error=None)
                if loss_breached:item.update(armed=False,last_error='daily_loss_limit')
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    for intent in updates:c.execute('UPDATE forward_paper_intents SET document=? WHERE client_order_id=?',(encoded(intent),intent['client_order_id']))
                    self._save(c,item)
                return item
            except Exception:
                self.disarm(identifier,'reconciliation_failed')
                with self.database.connect() as c:
                    failed=self.get(identifier);failed['reconciled']=False;self._save(c,failed)
                raise

    def arm(self,identifier):
        with self.lock:
            item=self.reconcile(identifier)
            with self.database.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                # One broker executor across experiments, not one per browser tab.
                others=[json.loads(r[0]) for r in c.execute('SELECT document FROM forward_paper WHERE id<>?',(identifier,))]
                if any(o['armed'] for o in others):raise ValueError('Another paper deployment is armed')
                item['armed']=True;self._save(c,item)
            return item

    def cancel_open(self,identifier):
        """Explicit cancellation only; it never assumes a position was closed."""
        with self.lock:
            self.disarm(identifier,'cancel_requested')
            self.reconcile(identifier,allow_risk_breach=True)
            for intent in self.intents(identifier):
                if intent['state'].lower() in TERMINAL:continue
                order=intent.get('broker',{})
                if not order.get('id'):raise ValueError('Unresolved submission requires broker reconciliation')
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE');self._owns(c)
                    self.client.cancel(order['id'])
            return self.reconcile(identifier,allow_risk_breach=True)

    def flatten(self,identifier):
        """Explicit risk-reducing action, permitted while disarmed or loss-limited."""
        with self.lock:
            self.disarm(identifier,'flatten_requested')
            item=self.reconcile(identifier,allow_risk_breach=True)
            quantity=number(item['position_qty'])
            if not quantity:return None
            # Unresolved orders must be cancelled and confirmed separately first.
            return self._submit(identifier,decision_at=self.clock(),action='exit',
                                direction='long' if quantity>0 else 'short',
                                price=item['position']['avg_entry_price'],emergency_exit=True)

    def protect_close(self,identifier):
        """Native MOC for an already reconciled position, never an entry promise.

        Alpaca has no documented atomic entry-plus-MOC order. Calling this after
        a fill therefore leaves a fill-to-protection gap; production arming stays
        disabled pending the user's decision on that limitation.
        """
        with self.lock:
            item=self.reconcile(identifier,allow_risk_breach=True)
            quantity=number(item['position_qty'])
            if not quantity:return None
            existing=[i for i in self.intents(identifier) if i.get('purpose')=='session_close' and i['state'].lower() not in TERMINAL]
            if existing:
                if len(existing)!=1:raise ValueError('Conflicting closing-auction protection')
                intent=existing[0]
                if intent['state'].lower() not in {'new','accepted','accepted_for_bidding'}:
                    raise ValueError('Closing-auction protection is not confirmed active')
                if number(intent['order']['qty'])!=abs(quantity) or intent['order']['side']!=('sell' if quantity>0 else 'buy'):
                    raise ValueError('Closing-auction protection does not cover broker position')
                return intent
            return self._submit(identifier,decision_at=self.clock(),action='exit',
                                direction='long' if quantity>0 else 'short',
                                price=item['position']['avg_entry_price'],emergency_exit=True,close_auction=True)

    def submit(self,identifier,*,decision_at,action,direction,price,stop_loss=None,sequence=0):
        return self._submit(identifier,decision_at=decision_at,action=action,direction=direction,
                            price=price,stop_loss=stop_loss,sequence=sequence)

    def _submit(self,identifier,*,decision_at,action,direction,price,stop_loss=None,sequence=0,emergency_exit=False,close_auction=False):
        """Called only by the independent B executor; no frontend arbitrary order API."""
        with self.lock:
            if action not in {'entry','exit'} or direction not in {'long','short'} or sequence!=0:
                raise ValueError('Unsupported paper intent')
            decision=stamp(decision_at);current=stamp(self.clock())
            client_id='ledger-b-'+digest(dict(deployment=identifier,decision=decision.isoformat(),action=action,direction=direction,sequence=sequence,purpose='session_close' if close_auction else 'strategy'))[:40]
            old=next((i for i in self.intents(identifier) if i['client_order_id']==client_id),None)
            if old:return old
            if emergency_exit and action!='exit':raise ValueError('Only exits may bypass paper arming')
            item=self.reconcile(identifier,allow_risk_breach=emergency_exit)
            if not item['armed'] and not emergency_exit:raise ValueError('Paper deployment is disarmed')
            if not 0<=(current-decision).total_seconds()<=95:raise ValueError('Paper signal is stale or from the future')
            clock=self.client.clock()
            if not clock.get('is_open'):raise ValueError('Paper market is closed')
            if abs((stamp(clock['timestamp'])-current).total_seconds())>30:raise ValueError('Broker clock is stale')
            if close_auction:
                if action!='exit':raise ValueError('Closing auction must reduce an existing position')
                # Conservatively use the calendar-relative ten-minute cutoff,
                # including shortened sessions; never queue the following day.
                if not clock.get('next_close') or current>=stamp(clock['next_close'])-timedelta(minutes=10):
                    raise ValueError('Closing-auction submission cutoff reached')
                if stamp(clock['next_close']).date()!=current.date():raise ValueError('Closing auction is not in the current session')
            intents=self.intents(identifier)
            if any(i['state'].lower() not in TERMINAL for i in intents):raise ValueError('A paper order is still unresolved')
            quantity=number(item['position_qty']);quote=number(price)
            if quote<=0:raise ValueError('Positive execution reference required')
            local=current.astimezone(ZoneInfo('America/New_York'))
            if action=='entry':
                if stop_loss is None or number(stop_loss)<=0:
                    raise ValueError('Initial strategy stop is required')
                if (direction=='long' and number(stop_loss)>=quote) or (direction=='short' and number(stop_loss)<=quote):
                    raise ValueError('Initial strategy stop is on the wrong side')
                if quantity:raise ValueError('Paper position must be flat before entry')
                if not (9*60+30<=local.hour*60+local.minute<11*60+30):raise ValueError('Outside frozen paper entry window')
                entries=[i for i in intents if i['action']=='entry' and stamp(i['decision_at']).astimezone(ZoneInfo('America/New_York')).date()==local.date()]
                if len(entries)>=3:raise ValueError('Three paper entry attempts already reserved this session')
                asset=self.client.asset()
                if not asset.get('tradable') or (direction=='short' and not asset.get('shortable')):raise ValueError('QQQ is not eligible for requested paper direction')
                cap=min(number(item['risk']['fixed_notional']),number(item['account_equity'])*number(item['risk']['max_equity_fraction']))
                qty=(cap/quote).to_integral_value(rounding=ROUND_DOWN)
                if qty<1:raise ValueError('Conservative paper cap cannot fund one whole share')
                side='buy' if direction=='long' else 'sell'
            else:
                if not quantity:raise ValueError('No broker paper position to exit')
                qty=abs(quantity);side='sell' if quantity>0 else 'buy'
            order=dict(symbol='QQQ',qty=str(qty),side=side,type='market',time_in_force='cls' if close_auction else 'day',extended_hours=False,client_order_id=client_id)
            intent=dict(client_order_id=client_id,deployment_id=identifier,decision_at=decision.isoformat(),
                        action=action,direction=direction,state='CREATED',order=order,stop_loss=stop_loss,
                        purpose='session_close' if close_auction else 'strategy')
            with self.database.connect() as c:
                c.execute('INSERT INTO forward_paper_intents VALUES (?,?,?)',(client_id,identifier,encoded(intent)))
            intent['state']='SUBMITTING'
            with self.database.connect() as c:c.execute('UPDATE forward_paper_intents SET document=? WHERE client_order_id=?',(encoded(intent),client_id))
            try:
                approval=self.client.authorize(order,current.timestamp()+15)
                # The intent above is already durable. Fence process replacement
                # across this single bounded POST; a newer process cannot arm in
                # the interval between the owner check and submission.
                with self.database.connect() as c:
                    c.execute('BEGIN IMMEDIATE');self._owns(c)
                    response=self.client.submit(order,approval)
                    if response.get('client_order_id')!=client_id:raise ValueError('Paper submission identity mismatch')
                    intent['state']='SUBMITTED'  # Submission is not a fill.
                    c.execute('UPDATE forward_paper_intents SET document=? WHERE client_order_id=?',(encoded(intent),client_id))
                return intent
            except Exception:
                self.disarm(identifier,'submission_unknown_reconcile_before_retry')
                raise
