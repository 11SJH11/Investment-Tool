from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import json
import pytest

from app.forward.deployments import Deployments, STRATEGIES, D6
from app.storage.database import Database
from app.storage.strategy_source_archive import manifest_for


ACCOUNT=dict(starting_balance=10000,risk_value=1,commission_per_order=.1,spread_bps=1,slippage_bps=1)

class Registry:
    def __init__(self):
        self.content={'fixture.py':b'# Archived text must never execute\nraise RuntimeError("do not import")\n'}
        self.keys=list(STRATEGIES.values())
    def executing(self):return nullcontext()
    def sources(self):return self.content.copy()
    def specs(self):return [SimpleNamespace(key=k,defaults={**D6,'extra_rule':7},research_parameters=[],timeframes=('1m','1d')) for k in self.keys]
    def provenance(self,key):
        _,fingerprint=manifest_for(self.content)
        return dict(key=key,module='app.backtesting.strategies.fixture',source_sha256=sha256(self.content['fixture.py']).hexdigest(),registry_sha256=fingerprint)

@pytest.fixture
def repository(tmp_path):
    db=Database(tmp_path/'test.db');db.initialize()
    return Deployments(db)

def test_four_independent_inactive_deployments_pin_exact_settings(repository):
    rows=repository.prepare('request',ACCOUNT,registry=Registry())
    assert {r['name'] for r in rows}==set(STRATEGIES)
    assert len({r['id'] for r in rows})==4
    for r in rows:
        d=r['definition'];s=r['state']
        assert d['mode']=='SHADOW' and d['symbol']=='QQQ' and d['primary_timeframe']=='1m'
        assert all(d['parameters'][k]==v for k,v in D6.items())
        assert d['parameters']['extra_rule']==7
        assert d['engine']['entry_windows']==[['09:30','11:30']]
        assert d['engine']['max_trades_per_day']==3 and not d['engine']['allow_overnight']
        assert s['status']=='DRAFT' and not s['execution_enabled'] and s['future_oos_started_at'] is None
        assert repository.verify_sources(r['id'])['verified']
    rows[0]['state']['trade_history'].append({'fake':True})
    assert all(not r['state']['trade_history'] for r in repository.list(rows[0]['experiment_id']))

def test_restart_idempotency_and_registry_edits_never_upgrade_existing_deployments(repository):
    registry=Registry();old=repository.prepare('request',ACCOUNT,registry=registry)
    registry.content['fixture.py']=b'# changed\n'
    restarted=Deployments(repository.database)
    assert restarted.prepare('request',ACCOUNT,registry=registry)==old
    newer=restarted.prepare('new-request',ACCOUNT,registry=registry)
    assert newer[0]['definition_sha256']!=old[0]['definition_sha256']
    assert restarted.verify_sources(old[0]['id'])['verified']
    with pytest.raises(ValueError,match='immutable'):
        restarted.prepare('request',{**ACCOUNT,'risk_value':2},registry=registry)

def test_missing_strategy_rolls_back_entire_group(repository):
    registry=Registry();registry.keys.pop()
    with pytest.raises(ValueError,match='not registered'):repository.prepare('bad',ACCOUNT,registry=registry)
    with repository.database.connect() as c:
        assert c.execute('SELECT count(*) FROM forward_deployments').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM forward_experiments').fetchone()[0]==0

@pytest.mark.parametrize('change',[{'risk_value':0},{'starting_balance':float('nan')},
    {'slippage_bps':-1},{'api_key':'secret'},{'mode':'LIVE'}])
def test_invalid_accounts_and_secrets_are_rejected(repository,change):
    with pytest.raises(ValueError):repository.prepare('bad',{**ACCOUNT,**change},registry=Registry())

@pytest.mark.parametrize('fault',['definition','blob','manifest'])
def test_archive_or_definition_corruption_fails_closed(repository,fault):
    row=repository.prepare('request',ACCOUNT,registry=Registry())[0]
    with repository.database.connect() as c:
        if fault=='definition':
            definition=deepcopy(row['definition']);definition['parameters']['entry_confirmation_bars']=99
            c.execute('UPDATE forward_deployments SET definition_json=? WHERE id=?',(json.dumps(definition),row['id']))
        elif fault=='blob':c.execute("UPDATE strategy_source_blobs SET content=?",(b'changed',))
        else:c.execute("DELETE FROM strategy_source_archives")
    with pytest.raises(ValueError):repository.verify_sources(row['id'])

def test_actual_baseline_contract_can_be_archived_without_execution(repository):
    from app.backtesting.strategies import strategy_registry
    # Test is portable where the user's local B/C/D modules are not installed.
    class BaselineRegistry:
        def executing(self):return strategy_registry.executing()
        def sources(self):return strategy_registry.sources()
        def provenance(self,key):return strategy_registry.provenance(next(iter(STRATEGIES.values())))
        def specs(self):
            baseline=next(s for s in strategy_registry.specs() if s.key==next(iter(STRATEGIES.values())))
            from dataclasses import replace
            return [replace(baseline,key=k) for k in STRATEGIES.values()]
    rows=repository.prepare('actual-baseline',ACCOUNT,registry=BaselineRegistry())
    assert all(repository.verify_sources(r['id'])['verified'] for r in rows)

def test_installed_frozen_four_strategy_contracts(repository):
    from app.backtesting.strategies import strategy_registry
    if not set(STRATEGIES.values()).issubset({s.key for s in strategy_registry.specs()}):
        pytest.skip('Optional local B/C/D source modules are not installed')
    rows=repository.prepare('installed-four',ACCOUNT)
    assert {r['definition']['strategy_key'] for r in rows}==set(STRATEGIES.values())
    for row in rows:
        key=row['definition']['strategy_key']
        assert row['definition']['implementation']==strategy_registry.provenance(key)
        assert repository.verify_sources(row['id'])['verified']

def test_repeated_initialization_preserves_other_application_data(repository):
    repository.database.set_setting('preservation-fixture','unchanged')
    original=repository.prepare('request',ACCOUNT,registry=Registry())
    repository.database.initialize()
    again=Deployments(repository.database)
    assert again.list(original[0]['experiment_id'])==original
    assert repository.database.get_setting('preservation-fixture')=='unchanged'
