"""A provider-independent adapter can use Journal persistence without schema changes."""
from copy import deepcopy
from hashlib import sha256

import pytest

from app.brokers.base import BrokerHistoryAdapter, HistoryBatch
from app.services.journal import JournalService
from app.storage.broker_sync_repository import BrokerSyncRepository
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


class ExampleHistory:
    provider = 'example'

    def __init__(self, account, environment='demo'):
        self.environment = environment
        self.account_key = sha256(f'{self.provider}:{environment}:{account}'.encode()).hexdigest()
        self.account_label = f'Example {environment} / {self.account_key[:8]}'

    def capability_report(self):
        return dict(provider=self.provider, read_only=True, execution=False, closed_trades=True)

    def accounts(self):
        return [dict(account_key=self.account_key, environment=self.environment, label=self.account_label)]

    def fetch_closed(self, cursor):
        return HistoryBatch([dict(source='broker_example', external_provider=self.provider,
            external_account_key=self.account_key, external_id=f'{self.environment}:{self.account_key}:10',
            account=self.account_label, ticker='TEST', direction='long', status='closed',
            opened_at='2026-09-01T12:00:00Z', closed_at='2026-09-02T12:00:00Z',
            entry_price=100, exit_price=112, quantity=5, account_currency='USD',
            position_currency='USD', broker_realized_pnl=60, pnl_amount=59, commission=1, fees=1,
            costs_complete=True, external_order_id='9', source_metadata={
                'entry_fills':[dict(id='11',quantity=5,price=100)],
                'exit_fills':[dict(id='12',quantity=3,price=110),dict(id='13',quantity=2,price=115)],
                'external_order_ids':['9','12','13'], 'environment':self.environment})], '13')

    def close(self):
        pass


def test_adapter_protocol_exposes_only_read_history_operations():
    expected={'capability_report','accounts','fetch_closed','close'}
    assert {k for k,v in vars(BrokerHistoryAdapter).items() if callable(v) and not k.startswith('_')} == expected
    assert all(callable(getattr(ExampleHistory('synthetic'), method)) for method in expected)


def test_new_provider_shared_journal_identity_reviews_fills_and_cursor(tmp_path):
    db=Database(tmp_path/'ledger.sqlite');db.initialize()
    sync=BrokerSyncRepository(db);repo=JournalRepository(db);journal=JournalService(repo)
    adapters=[ExampleHistory('a'),ExampleHistory('b'),ExampleHistory('a','live')]
    for adapter in adapters:
        assert sync.commit(adapter,adapter.fetch_closed(None),None)['created']==1
    assert len(repo.list_trades())==3
    adapter=adapters[0];batch=adapter.fetch_closed('13');facts=batch.trades[0]
    row=repo.get_by_external(source=facts['source'],external_provider=adapter.provider,external_id=facts['external_id'])
    journal.update_trade(row['id'],{'notes':'Keep review','review_data':{'custom':{'field':'answer'}}})
    repo.add_attachment(dict(owner_type='trade',owner_id=row['id'],original_name='proof.png',stored_name='proof.png',mime_type='image/png'))
    facts['notes']='Provider must not overwrite review'
    assert sync.commit(adapter,deepcopy(batch),'13')['created']==0
    saved=repo.get_trade(row['id'])
    assert saved['notes']=='Keep review' and saved['review_data']['custom']=={'field':'answer'}
    assert saved['source_metadata']['exit_fills']==[dict(id='12',quantity=3,price=110),dict(id='13',quantity=2,price=115)]
    assert saved['pnl_amount']==59 and saved['broker_realized_pnl']==60
    for field in ('entry_price','quantity','broker_realized_pnl','source_metadata'):
        with pytest.raises(ValueError,match='read-only'):
            journal.update_trade(row['id'],{field:999})
    with pytest.raises(ValueError,match='Another sync'):
        sync.commit(adapter,batch,None)
    db.initialize();db.initialize()
    assert repo.get_trade(row['id'])==saved
    assert len(repo.attachments('trade',row['id']))==1
    assert sync.state(adapter.provider,adapter.account_key)['cursor']=='13'
