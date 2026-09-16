from copy import deepcopy

import pytest

from app.brokers.base import BrokerHistoryError, HistoryBatch
from app.core.config import Settings
from app.services.broker_sync import BrokerSyncService
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from tests.test_oanda_journal_import import adapter, history


@pytest.mark.parametrize('token,account', [(None,None), ('synthetic',None), (None,'synthetic'), (' ','synthetic')])
def test_incomplete_configuration_makes_zero_history_calls(tmp_path, token, account):
    settings = Settings(_env_file=None, OANDA_ACCESS_TOKEN=token, OANDA_ACCOUNT_ID=account)
    def forbidden(*args):
        pytest.fail('Unconfigured broker constructed a history adapter')
    service = BrokerSyncService(settings, Database(tmp_path/'db'), forbidden)
    assert service.status()['status'] == 'not_configured'
    assert service.sync()['status'] == 'not_configured'


def test_atomic_sync_preserves_review_and_account_identity(tmp_path):
    db = Database(tmp_path/'db'); db.initialize()
    repo = JournalRepository(db); journal = JournalService(repo)
    broker = adapter()
    trade, opening, closing, protection = history()
    facts = broker._map(trade, opening, closing, protection, 'USD')
    broker.fetch_closed = lambda cursor: HistoryBatch([deepcopy(facts)], '30')
    broker.close = lambda: None
    settings = Settings(_env_file=None, OANDA_ACCESS_TOKEN='synthetic', OANDA_ACCOUNT_ID='synthetic')
    sync = BrokerSyncService(settings, db, lambda *args: broker)
    assert sync.sync()['created'] == 1
    row = repo.list_trades()[0]
    review = {'notes':'Keep me', 'setup_grade':'A', 'review_data':{'mistakes':['rushed'], 'custom':{'1:field':'original answer'}}}
    journal.update_trade(row['id'], review)
    repo.add_attachment({'owner_type':'trade','owner_id':row['id'],'original_name':'old.png','stored_name':'old.png','mime_type':'image/png'})
    facts['pnl_amount'] = 5
    facts['notes'] = 'Provider must not own notes'
    assert sync.sync()['updated'] == 1
    saved = repo.get_trade(row['id'])
    assert saved['pnl_amount'] == 5 and saved['notes'] == 'Keep me'
    assert saved['review_data'] == review['review_data']
    assert len(repo.attachments('trade',row['id'])) == 1
    assert 'original_import' in saved['source_metadata']
    journal.update_trade(row['id'], {'notes':'Edited review'})
    assert repo.get_trade(row['id'])['pnl_amount'] == 5
    with pytest.raises(ValueError, match='read-only'):
        journal.update_trade(row['id'], {'quantity':999})
    before = sync.repository.state('oanda',broker.account_key)['cursor']
    broken = {**facts, 'external_id':'bad', 'direction':'invalid'}
    broker.fetch_closed = lambda cursor: HistoryBatch([{**facts,'pnl_amount':999},broken], '31')
    with pytest.raises(BrokerHistoryError):
        sync.sync()
    assert repo.get_trade(row['id'])['pnl_amount'] == 5
    assert sync.repository.state('oanda',broker.account_key)['cursor'] == before
    other = adapter(account='other-account')
    assert other._map(trade,opening,closing,protection,'USD')['external_id'] != facts['external_id']
    other.close()


def test_busy_sync_does_not_call_adapter(tmp_path):
    settings = Settings(_env_file=None,OANDA_ACCESS_TOKEN='synthetic',OANDA_ACCOUNT_ID='synthetic')
    service = BrokerSyncService(settings,Database(tmp_path/'db'),lambda *args: pytest.fail('network'))
    service._lock.acquire()
    with pytest.raises(BrokerHistoryError, match='already running'):
        service.sync()


def test_stale_cursor_cannot_overwrite_other_process_sync(tmp_path):
    db=Database(tmp_path/'db');db.initialize()
    settings=Settings(_env_file=None,OANDA_ACCESS_TOKEN='synthetic',OANDA_ACCOUNT_ID='synthetic')
    service=BrokerSyncService(settings,db)
    broker=adapter()
    service.repository.commit(broker,HistoryBatch([],'30'),None)
    with pytest.raises(ValueError,match='Another sync'):
        service.repository.commit(broker,HistoryBatch([],'29'),None)
    assert service.repository.state('oanda',broker.account_key)['cursor']=='30'
    broker.close()
