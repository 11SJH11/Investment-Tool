"""Journal confirmed paper positions using the existing canonical broker model.

Orders supply cumulative fill aggregates, not individual executions or net P&L.
No network requests, shadow fills, fee estimates or new order capabilities.
"""
from decimal import Decimal
from types import SimpleNamespace

from app.brokers.base import HistoryBatch
from app.brokers.executions import Execution, account_key, closed_positions
from app.storage.broker_sync_repository import BrokerSyncRepository
from .bars import stamp
from .deployments import digest
from .paper_gateway import TERMINAL, number


class PaperJournal:
    def __init__(self, gateway):
        self.gateway = gateway
        self.repository = BrokerSyncRepository(gateway.database)

    def sync(self, identifier):
        with self.gateway.lock:
            item = self.gateway.get(identifier)
            if not item['reconciled'] or not item['account_id']:
                return {'created': 0, 'updated': 0}
            key = account_key('alpaca_paper', 'paper', 'paper-api.alpaca.markets', item['account_id'])
            adapter = SimpleNamespace(provider='alpaca_paper', environment='paper', account_key=key)
            executions, origins = [], {}
            balance = Decimal(0)
            position = None
            entry_time = None
            for intent in self.gateway.intents(identifier):
                # Never publish a still-changing aggregate. Revisit on a later poll.
                if intent['state'].lower() not in TERMINAL:
                    break
                facts = intent.get('broker')
                if not facts:
                    raise ValueError('Paper Journal requires reconciled terminal order facts')
                quantity = number(facts['filled_qty'])
                if not quantity:
                    continue
                timestamp = facts.get('filled_at') or intent.get('first_fill_observed_at')
                if not timestamp:
                    raise ValueError('Paper Journal lacks fill timestamp evidence')
                timestamp = stamp(timestamp).isoformat()
                if intent['action'] == 'entry':
                    if balance:
                        raise ValueError('Overlapping paper entries require reconciliation')
                    position = identifier+':'+intent['client_order_id']
                    origins[position] = intent
                    entry_time = stamp(timestamp)
                    balance = quantity
                else:
                    if not position or quantity > balance or stamp(timestamp) <= entry_time:
                        raise ValueError('Paper exit chronology or quantity is ambiguous')
                    balance -= quantity
                executions.append(Execution(provider=adapter.provider, environment='paper', account_key=key,
                    external_id=identifier+':'+intent['client_order_id'], order_id=facts['id'],
                    position_id=position, symbol='QQQ', asset_class='equity', side=facts['side'],
                    quantity=str(quantity), price=str(facts['filled_avg_price']), timestamp=timestamp,
                    quantity_unit='shares', role=intent['action'], evidence='reconciled_order_snapshot',
                    metadata=dict(programmatic_order=True, client_order_id=intent['client_order_id'],
                        decision_at=intent['decision_at'], purpose=intent['purpose'],
                        timestamp_basis='broker_completed_fill' if facts.get('filled_at') else 'first_observed_fill')))
            trades = closed_positions(executions, 'Alpaca paper / '+key[:8], 'USD',
                                      {position} if balance else ())
            for trade in trades:
                origin = origins[trade['source_metadata']['position_id']]
                trade.update(is_automated=True, execution_source='strategy', strategy_id=item['strategy_key'],
                             strategy_name=item['strategy_key'], strategy_run_id=identifier,
                             stop_loss=origin.get('stop_loss'))
                trade['source_metadata'].update(mode='ALPACA_PAPER', deployment_id=identifier,
                    experiment_id=item['experiment_id'], definition_sha256=item['definition_sha256'],
                    source_archive=item['definition']['source_archive'], decision_at=origin['decision_at'],
                    timestamp_basis='per_order_evidence',
                    fill_note='Cumulative broker order fills; observation timestamps are not exact execution times')
            cursor = digest([identifier, [e.payload() for e in executions]])
            previous = self.repository.state(adapter.provider, key).get('cursor')
            if cursor == previous:
                return {'created': 0, 'updated': 0}
            return self.repository.commit(adapter, HistoryBatch(trades, cursor, [e.payload() for e in executions]), previous)
