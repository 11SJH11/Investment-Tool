import json
import pytest
from app.core.automation import automation_fields
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.services.journal import JournalService
from tests.test_journal_v2 import trade

@pytest.mark.parametrize('source,expected,origin',[('paper_manual',False,'manual'),('live_manual',False,'manual'),('replay',False,'manual'),('backtest',True,'strategy'),('broker_mt5',None,'imported'),('broker_oanda',None,'imported')])
def test_provenance_never_guesses_from_account_or_provider(source,expected,origin):
    fields=automation_fields({'source':source,'account':'Automated bot account'})
    assert fields['is_automated'] is expected and fields['execution_source']==origin

def test_persistence_filters_and_repeat_migration(tmp_path):
    db=Database(tmp_path/'journal');db.initialize();repo=JournalRepository(db);service=JournalService(repo)
    manual=trade(service,notes='preserve me')
    auto=trade(service,source='backtest',source_metadata={'strategy_key':'fixture','strategy_name':'Fixture','run_id':'run-1'})
    assert auto['is_automated'] is True and auto['strategy_id']=='fixture' and auto['strategy_run_id']=='run-1'
    assert manual['is_automated'] is False
    assert [r['id'] for r in repo.filtered_trades({'dimensions_json':json.dumps({'automation_type':['Automated']})})]==[auto['id']]
    # Simulate pre-migration rows before running initialization again.
    with db.connect() as c:c.execute("UPDATE journal_trades SET is_automated=NULL,execution_source='unknown'")
    db.initialize();db.initialize()
    assert repo.get_trade(manual['id'])['notes']=='preserve me'
    assert repo.get_trade(manual['id'])['is_automated'] is False
    assert repo.get_trade(auto['id'])['is_automated'] is True
    assert repo.get_trade(auto['id'])['strategy_id']=='fixture'

def test_trusted_automation_evidence_is_structured():
    result=automation_fields({'source':'broker_mt5','execution_source':'agent','strategy_id':'known-id'})
    assert result['is_automated'] is True and result['execution_source']=='agent'
