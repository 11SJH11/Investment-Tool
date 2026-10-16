"""Project durable shadow results into Journal without changing execution evidence.

Closed simulated trades only. This is not a broker import or a fill inference.
The stable identity includes the deployment so independent accounts cannot merge.
"""
import json

from app.storage.journal_repository import TRADE_COLUMNS, _encode
from .deployments import Deployments, digest, now


class ShadowJournal:
    def __init__(self, database):
        self.database = database

    def sync(self, experiment):
        created = 0
        with self.database.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows = Deployments._list(self, c, experiment)
            feed = c.execute('SELECT identity_json,start_at FROM forward_feeds WHERE experiment_id=?',
                             (experiment,)).fetchone()
            for row in rows:
                definition = row['definition']
                for trade in row['state']['trade_history']:
                    external = digest([row['id'], trade['entry_time'], trade['direction']])
                    fingerprint = digest(trade)
                    existing = c.execute('SELECT source_metadata FROM journal_trades WHERE source=? AND external_provider=? AND external_id=?',
                                         ('forward_shadow', 'ledger', external)).fetchone()
                    if existing:
                        if json.loads(existing[0]).get('trade_sha256') != fingerprint:
                            raise ValueError('Closed shadow trade changed after Journal publication')
                        continue  # Preserve all review fields, attachments, IDs and timestamps.
                    metadata = dict(mode='SHADOW', simulated=True, experiment_id=experiment,
                        deployment_id=row['id'], deployment_name=row['name'],
                        definition_sha256=row['definition_sha256'],
                        source_archive=definition['source_archive'], implementation=definition['implementation'],
                        parameters=definition['parameters'], engine=definition['engine'],
                        feed=json.loads(feed['identity_json']) if feed else None,
                        forward_start_at=feed['start_at'] if feed else None,
                        quantity_unit='shares', trade_sha256=fingerprint, trade=trade)
                    data = dict(source='forward_shadow', external_provider='ledger', external_id=external,
                        external_account_key=row['id'], account=row['name']+' / '+row['id'][:8],
                        is_automated=True, execution_source='strategy', strategy_id=definition['strategy_key'],
                        strategy_name=definition['strategy_key'], strategy_run_id=row['id'],
                        name=row['name'], ticker=trade['symbol'], direction=trade['direction'], status='closed',
                        opened_at=trade['entry_time'], closed_at=trade['exit_time'],
                        entry_price=trade['entry_price'], exit_price=trade['exit_price'], quantity=trade['quantity'],
                        stop_loss=trade['stop_loss'], take_profit=trade['take_profit'], fees=trade['fees'],
                        result=trade['result'], result_source='computed', pnl_amount=trade['net_pnl'],
                        pnl_pct=trade['pnl_pct'], r_multiple=trade['r_multiple'], planned_rr=trade['planned_rr'],
                        pnl_source='simulated_engine', position_currency='USD', account_currency='USD',
                        initial_risk_amount=trade['initial_risk_amount'], risk_source='simulated_engine',
                        costs_complete=True, source_metadata=metadata, imported_at=now())
                    c.execute(f"INSERT INTO journal_trades({','.join(TRADE_COLUMNS)}) VALUES ({','.join('?' for _ in TRADE_COLUMNS)})",
                              [_encode(data.get(k), k) for k in TRADE_COLUMNS])
                    created += 1
        return created
