import json
import sqlite3
from types import SimpleNamespace
import pytest
from tools import verify_gold_campaign_baseline as verifier


@pytest.fixture
def original(tmp_path,monkeypatch):
    root=tmp_path/'backend';(root/'data').mkdir(parents=True)
    payload=dict(strategy_key='gold_asia_15m_ifvg_research_v1',symbols=['XAUUSD'],
        start_date='2024-01-02',end_date='2024-01-03',warmup_start_date='2024-01-01',save_run=True)
    campaign=dict(status='DEVELOPMENT_COMPLETE',execution=dict(entries=[dict(payload=payload,plan_key='gold',max_minutes=1)]),
        plans={'gold':dict(development=dict(start='2024-01-02',end='2024-01-03'),warmup=dict(start='2024-01-01'),coverage=dict(provider_namespace='oanda-mid-v1'))})
    with sqlite3.connect(root/'data/ledger.db') as c:
        c.execute('CREATE TABLE agent_campaigns(id TEXT,document TEXT)')
        c.execute('CREATE TABLE agent_datasets(document TEXT)')
        c.execute('INSERT INTO agent_campaigns VALUES(?,?)',('fixture',json.dumps(campaign)))
    monkeypatch.setattr(verifier,'ROOT',root)
    monkeypatch.setattr('sys.argv',['verify','--campaign-id','fixture'])
    return root,campaign


def test_verifier_preserves_original_and_does_not_persist_user_run(original,monkeypatch):
    root,campaign=original
    before=(root/'data/ledger.db').read_bytes()
    from app.services.backtest import BacktestService
    def run(self,payload,progress):
        assert self.runs is None and payload=={**campaign['execution']['entries'][0]['payload'],'save_run':False}
        with pytest.raises(ValueError,match='bounds'):
            self.market_data.get_bars('QQQ','1m',None,None)
        return dict(trades=[],strategy={'implementation':{'fixture':True}},data={})
    monkeypatch.setattr(BacktestService,'run',run)
    verifier.main()
    assert (root/'data/ledger.db').read_bytes()==before
    manifest=json.loads(next((root/'data/research_verification').glob('*/manifest.json')).read_text())
    assert manifest['status']=='COMPLETED' and manifest['holdout_access'] is False


def test_verifier_refuses_protected_overlap_before_engine(original,monkeypatch):
    root,_=original
    with sqlite3.connect(root/'data/ledger.db') as c:
        c.execute('INSERT INTO agent_datasets VALUES(?)',(json.dumps(dict(symbols=['XAUUSD'],state='LOCKED_HOLDOUT',start='2024-01-03',end='2024-02-01')),))
    with pytest.raises(ValueError,match='protected'):
        verifier.main()
    assert not (root/'data/research_verification').exists()


def test_verifier_refuses_config_window_changes(original):
    root,campaign=original
    campaign['execution']['entries'][0]['payload']['end_date']='2024-01-04'
    with sqlite3.connect(root/'data/ledger.db') as c:
        c.execute('UPDATE agent_campaigns SET document=?',(json.dumps(campaign),))
    with pytest.raises(ValueError,match='declared development'):
        verifier.main()
