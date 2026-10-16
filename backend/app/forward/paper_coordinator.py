"""Bounded paper orchestration; only the durable gateway can submit an order.

Construction never arms or contacts a provider. Restart disarming is owned by the
gateway. The caller supplies the shared completed-bar service, not shadow fills.
"""
from datetime import timedelta
import json
from .bars import stamp
from .deployments import encoded
from .paper_evaluator import PaperEvaluator
from .paper_gateway import number
from .paper_protection import PaperProtection,ACK


class PaperCoordinator:
    def __init__(self,database,runtime,gateway):
        self.database=database;self.runtime=runtime;self.gateway=gateway
        self.evaluator=PaperEvaluator(database,runtime,gateway)
        self.protection=PaperProtection(gateway)
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_paper_dispatches(
                deployment_id TEXT NOT NULL,decision_at TEXT NOT NULL,document TEXT NOT NULL,
                PRIMARY KEY(deployment_id,decision_at),
                FOREIGN KEY(deployment_id) REFERENCES forward_paper(id))''')

    def arm(self,identifier,acknowledgement=None):
        if acknowledgement!=ACK:raise ValueError('Explicit paper post-fill protection gap acknowledgement required')
        with self.gateway.lock:
            self._validate_history_for_arm(identifier)
            protection=self.protection.maintain(identifier)
            if protection['status'] not in {'FLAT','PROTECTED'}:raise ValueError('Paper protection is not ready for arming')
            item=self.gateway.get(identifier)
            item['protection_acknowledgement']=ACK
            item.setdefault('start_after',stamp(self.gateway.clock()).isoformat())
            with self.database.connect() as c:self.gateway._save(c,item)
            return self.gateway.arm(identifier)

    def _validate_history_for_arm(self,identifier):
        with self.gateway.lock:
            item=self.gateway.get(identifier)
            _,frame,_,_=self.runtime._history(item['experiment_id'])
            if frame.empty:raise ValueError('Paper history is not prepared')
            current=stamp(self.gateway.clock())
            if not 0<=(current-frame.available_at.iloc[-1]).total_seconds()<=95:
                raise ValueError('Fresh completed IEX bars are required before arming')
            source=next(r for r in self.runtime.deployments.list(item['experiment_id']) if r['definition']['strategy_key']==item['strategy_key'])
            self.runtime._verify(source)
            with self.database.connect() as c:
                decisions=c.execute('SELECT max(decision_at) FROM forward_paper_decisions WHERE deployment_id=?',(identifier,)).fetchone()[0]
            if decisions and len(frame.loc[frame.available_at>stamp(decisions)])>1:
                raise ValueError('Missed paper decisions require a new experiment; historical orders cannot be replayed')
            return item

    def tick(self,identifier):
        with self.gateway.lock:
            item=self.gateway.get(identifier)
            if not item['armed'] and not self.gateway.intents(identifier):return {'status':'DISARMED'}
            try:
                protection=self.protection.maintain(identifier)
                item=self.gateway.get(identifier)
                if protection['status'] not in {'FLAT','PROTECTED'}:return protection
                feed,frame,_,_=self.runtime._history(item['experiment_id'])
                current=stamp(self.gateway.clock())
                sessions=json.loads(feed['sessions_json'])
                session=next((s for s in sessions if stamp(s['open'])<=current<stamp(s['close'])),None)
                if session is None:
                    if number(item['position_qty']):raise ValueError('Paper position outside provider trading session')
                    return {'status':'OUTSIDE_SESSION'}
                # Leave native protection at the broker; no Ledger timer replacement.
                if current>=stamp(session['close'])-timedelta(minutes=10):return protection
                if not item['armed']:return {'status':'DISARMED'}
                if frame.empty or not 0<=(current-frame.available_at.iloc[-1]).total_seconds()<=95:
                    raise ValueError('Paper IEX data is stale')
                latest=frame.available_at.iloc[-1]
                if latest<=stamp(item['start_after']):return {'status':'AWAITING_NEXT_COMPLETED_BAR'}
                with self.database.connect() as c:
                    unresolved=[json.loads(r[0]) for r in c.execute('SELECT document FROM forward_paper_dispatches WHERE deployment_id=?',(identifier,))]
                    if any(r['status']=='DISPATCH_RESERVED' for r in unresolved):
                        raise ValueError('Interrupted paper dispatch requires review; no automatic retry')
                    old=c.execute('SELECT document FROM forward_paper_dispatches WHERE deployment_id=? AND decision_at=?',(identifier,latest.isoformat())).fetchone()
                if old:return json.loads(old[0])
                observation=self.evaluator.evaluate(identifier,latest)
                result=observation['result']
                dispatch={'status':'NO_SIGNAL','decision_at':latest.isoformat()}
                # Record before contacting the broker; a crash never replays a market order.
                with self.database.connect() as c:
                    c.execute('INSERT INTO forward_paper_dispatches VALUES (?,?,?)',
                              (identifier,latest.isoformat(),encoded({'status':'DISPATCH_RESERVED','decision_at':latest.isoformat()})))
                if result:
                    signal=result['signal'];action=result['kind']
                    direction=signal['direction'] if action=='entry' else observation['position']['direction'] if observation['position'] else None
                    if direction is None:dispatch['status']='NO_BROKER_POSITION'
                    elif action=='exit':
                        outcome=self.protection.request_exit(identifier,signal.get('reason','strategy_exit'))
                        dispatch.update(status=outcome['status'],protection=outcome)
                    else:
                        intent=self.gateway.submit(identifier,decision_at=latest,action=action,direction=direction,
                                                   price=float(frame.close.iloc[-1]),stop_loss=signal.get('stop_loss'))
                        dispatch.update(status='INTENT_SUBMITTED',client_order_id=intent['client_order_id'])
                with self.database.connect() as c:
                    c.execute('UPDATE forward_paper_dispatches SET document=? WHERE deployment_id=? AND decision_at=?',
                              (encoded(dispatch),identifier,latest.isoformat()))
                return dispatch
            except Exception:
                self.gateway.disarm(identifier,'paper_coordinator_requires_review')
                raise
