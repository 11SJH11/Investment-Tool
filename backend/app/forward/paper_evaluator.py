"""Independent B decisions, replayed against recorded broker-position observations.

No broker submission and no shadow-position consumption. This evaluator accepts
only immutable completed data and reconciled broker facts. Stored context is data,
never executable strategy state. An orchestration layer must explicitly authorize
and dispatch any returned intent through the paper risk gateway.
"""
from dataclasses import asdict
import json
from threading import RLock
from app.backtesting.context import StrategyContext
from app.backtesting.models import Position,EntrySignal,ExitSignal
from app.services.chart_data import prepare_chart_bars
from .bars import stamp
from .deployments import digest,encoded
from .paper_gateway import B_KEY,number
from .runtime import serial,runtime_identity


class PaperEvaluator:
    def __init__(self,database,shadow_runtime,gateway):
        self.database=database;self.runtime=shadow_runtime;self.gateway=gateway;self.lock=RLock()
        with database.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS forward_paper_decisions(
                deployment_id TEXT NOT NULL,decision_at TEXT NOT NULL,document TEXT NOT NULL,sha256 TEXT NOT NULL,
                PRIMARY KEY(deployment_id,decision_at),
                FOREIGN KEY(deployment_id) REFERENCES forward_paper(id))''')

    def _position(self,item):
        quantity=number(item['position_qty'])
        if not quantity:return None
        entries=[i for i in self.gateway.intents(item['id']) if i['action']=='entry' and number(i.get('broker',{}).get('filled_qty',0))>0]
        if not entries:raise ValueError('No reconciled entry for broker position')
        entry=entries[-1];facts=entry['broker'];direction='long' if quantity>0 else 'short'
        if entry['direction']!=direction:raise ValueError('Broker direction differs from entry intent')
        price=float(number(item['position']['avg_entry_price']))
        if price<=0:raise ValueError('Invalid broker entry price')
        stop=float(number(entry['stop_loss']));risk=abs(price-stop)
        if risk<=0:raise ValueError('Invalid broker entry risk')
        return Position(symbol='QQQ',direction=direction,entry_time=stamp(facts['filled_at'] or entry['first_fill_observed_at']),
                        entry_price=price,quantity=float(abs(quantity)),stop_loss=stop,take_profit=None,
                        initial_risk_per_share=risk,initial_risk_amount=risk*float(abs(quantity)),
                        metadata={'execution':'alpaca_paper','client_order_id':entry['client_order_id'],
                                  'entry_time_basis':'broker_filled_at' if facts['filled_at'] else 'first_fill_observed_at'})

    @staticmethod
    def _decision(strategy,frame,observation):
        native=frame.drop(columns=['available_at'])
        frames={'1m':native}
        for tf in strategy.spec.timeframes:
            if tf=='1m':continue
            if tf!='15m':raise ValueError('Unsupported paper timeframe')
            frames[tf]=prepare_chart_bars(native,tf,'regular')[0]
        position=observation['position']
        if position:
            position={**position,'entry_time':stamp(position['entry_time'])}
            position=Position(**position)
        ctx=StrategyContext(symbol='QQQ',primary_timeframe='1m',decision_time=stamp(observation['decision_at']),
                            frames=frames,position=position,equity=observation['equity'],
                            concepts=getattr(strategy.spec,'concepts',None))
        signal=strategy.on_bar(ctx)
        if signal is None:return None
        if not isinstance(signal,(EntrySignal,ExitSignal)):raise ValueError('Unsupported paper strategy signal')
        if isinstance(signal,EntrySignal) and signal.order_type!='market':raise ValueError('Paper baseline requires market entry')
        return {'kind':'entry' if isinstance(signal,EntrySignal) else 'exit','signal':serial(asdict(signal))}

    def evaluate(self,identifier,decision_at):
        with self.lock,self.runtime.registry.executing():
            item=self.gateway.get(identifier)
            if item['strategy_key']!=B_KEY:raise ValueError('Only frozen B is eligible for paper evaluation')
            if not item['reconciled']:raise ValueError('Broker reconciliation required')
            decision=stamp(decision_at)
            if abs((stamp(item['reconciled_at'])-decision).total_seconds())>95:
                raise ValueError('Broker observation is stale')
            rows=self.runtime.deployments.list(item['experiment_id'])
            source=next(r for r in rows if r['definition']['strategy_key']==B_KEY)
            self.runtime._verify(source)
            if source['definition_sha256']!=item['definition_sha256'] or digest(item['definition'])!=item['definition_sha256']:
                raise ValueError('Paper frozen definition changed')
            _,frame,_,_=self.runtime._history(item['experiment_id'])
            available=frame.loc[frame.available_at<=decision]
            if available.empty or available.available_at.iloc[-1]!=decision:
                raise ValueError('Exact completed paper decision bar required')
            # Never evaluate a stale historical decision as if it were current.
            if decision!=frame.available_at.iloc[-1]:raise ValueError('Only latest completed paper bar may be evaluated')
            with self.database.connect() as c:
                saved=list(c.execute('SELECT document,sha256 FROM forward_paper_decisions WHERE deployment_id=? ORDER BY decision_at',(identifier,)))
            records=[]
            for row in saved:
                record=json.loads(row[0])
                if digest(record)!=row[1]:raise ValueError('Paper decision integrity failure')
                records.append(record)
            if records and stamp(records[-1]['decision_at'])>decision:raise ValueError('Paper decisions must be chronological')
            strategy=self.runtime.registry.create(B_KEY,**item['definition']['parameters']);strategy.reset()
            for record in records:
                if record['runtime_identity']!=runtime_identity():raise ValueError('Paper runtime changed')
                visible=frame.loc[frame.available_at<=stamp(record['decision_at'])]
                if self._decision(strategy,visible,record)!=record['result']:
                    raise ValueError('Paper strategy replay diverged')
            if records and records[-1]['decision_at']==decision.isoformat():return records[-1]
            if records:
                unseen=frame.loc[(frame.available_at>stamp(records[-1]['decision_at']))&(frame.available_at<=decision)]
                if len(unseen)!=1:raise ValueError('Missed paper decisions require reconciliation; no historical orders')
            position=self._position(item)
            record=dict(deployment_id=identifier,decision_at=decision.isoformat(),
                        evaluated_at=stamp(self.gateway.clock()).isoformat(),broker_observed_at=item['reconciled_at'],
                        position=serial(asdict(position)) if position else None,
                        equity=float(number(item['account_equity'])),runtime_identity=runtime_identity())
            record['result']=self._decision(strategy,available,record)
            with self.database.connect() as c:
                c.execute('INSERT INTO forward_paper_decisions VALUES (?,?,?,?)',(identifier,decision.isoformat(),encoded(record),digest(record)))
            return record
