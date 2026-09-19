import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from app.api.dependencies import get_services
from app.api.strategy_workspace import router, workspace as workspace_dependency
from app.core.config import Settings
from app.services.strategy_workspace import StrategyWorkspace, _redact, syntax, template
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore


@pytest.fixture
def workspace(tmp_path): return StrategyWorkspace(tmp_path/'strategies')


def test_save_load_and_static_actions_do_not_execute(workspace, tmp_path):
    marker=tmp_path/'executed.txt'
    source=f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"+template()
    assert syntax(source)['ok']
    saved=workspace.save('_workspace_my_strategy.py',source)
    assert saved['ok'] and not marker.exists()
    assert workspace.read(saved['filename'])['source'] == source
    assert workspace.list()['files'] == [{'filename':saved['filename'],'read_only':False}]
    assert not marker.exists()
    assert workspace.execute('interface',saved['filename'],source,trusted=True)['ok']
    assert marker.read_text() == 'executed'


@pytest.mark.parametrize('filename', ['../bad.py','/tmp/bad.py','C:\\bad.py','_workspace_../bad.py',
    '_workspace_x.py:stream','_workspace_x.PY','reference.py','xau_liquidity_type3.py',
    'momentum_vcp_breakout_baseline_v1.py','__init__.py','base.py','registry.py'])
def test_safe_filenames_and_builtin_protection(workspace,filename):
    with pytest.raises(ValueError): workspace.save(filename,template())


def test_optimistic_save_and_builtin_read(workspace):
    first=workspace.save('_workspace_my_strategy.py',template())
    with pytest.raises(ValueError,match='Reload'): workspace.save(first['filename'],template()+'\n')
    updated=workspace.save(first['filename'],template()+'\n',first['revision'])
    assert updated['revision'] != first['revision']
    with pytest.raises(ValueError,match='Reload'): workspace.save(first['filename'],template(),first['revision'])
    (workspace.root/'reference.py').write_text('builtin = True')
    assert workspace.read('reference.py')['read_only']


def test_syntax_errors_and_size_limit(workspace):
    assert syntax('def broken(:')['line'] == 1
    assert not workspace.save('_workspace_bad.py','def broken(:')['ok']
    assert not workspace.root.exists()
    with pytest.raises(ValueError,match='100 KB'): syntax('#'+'x'*100_000)


def test_explicit_execution_acknowledgement(workspace):
    with pytest.raises(ValueError,match='acknowledgement'):
        workspace.execute('interface','_workspace_my_strategy.py',template())


def test_startup_discovery_never_imports_workspace_drafts(monkeypatch):
    import importlib
    import pkgutil
    import app.backtesting.strategies as package
    original = pkgutil.iter_modules
    def modules(path):
        yield from original(path)
        yield pkgutil.ModuleInfo(None, '_workspace_untrusted_draft', False)
    monkeypatch.setattr(pkgutil, 'iter_modules', modules)
    # Any attempt to import this draft would fail: it has no installed module.
    # Reload runs the real startup discovery path, rather than a copied filter.
    importlib.reload(package)


@pytest.mark.parametrize('source,expected', [
    ('x = 1','Exactly one'),
    (template().replace('workspace_my_strategy','wrong_key'),'must be workspace_my_strategy'),
    (template().replace('def on_bar(self, ctx):','async def on_bar(self, ctx):'),'synchronous'),
    (template().replace('("5m",)','("2m",)'),'supported timeframes'),
])
def test_invalid_interface(workspace,source,expected):
    result=workspace.execute('interface','_workspace_my_strategy.py',source,trusted=True)
    assert not result['ok'] and expected in result['message']


def test_strategy_tests_pass_fail_and_missing(workspace):
    result=workspace.execute('tests','_workspace_my_strategy.py',template(),trusted=True)
    assert result['ok'] and len(result['tests']) == 1
    result=workspace.execute('tests','_workspace_my_strategy.py',template()+'\ndef test_failure():\n    assert False\n',trusted=True)
    assert not result['ok'] and len(result['tests']) == 2
    source=template().split('def test_strategy():')[0]
    assert 'No test_' in workspace.execute('tests','_workspace_my_strategy.py',source,trusted=True)['message']


def test_timeout(workspace):
    workspace.timeout=.5
    result=workspace.execute('interface','_workspace_my_strategy.py','while True: pass',trusted=True)
    assert not result['ok'] and 'timed out' in result['message']


def test_output_and_exception_secrets_are_withheld(workspace):
    secret='never-return-this-test-secret'
    source=f"import sys\nprint({secret!r})\nprint({secret!r},file=sys.stderr)\n"+template()
    result=workspace.execute('interface','_workspace_my_strategy.py',source,trusted=True)
    assert result['ok'] and result['output']['stdout_characters'] > 0
    assert secret not in json.dumps(result)
    failed=workspace.execute('interface','_workspace_my_strategy.py',f'raise ValueError({secret!r})',trusted=True)
    assert not failed['ok'] and failed['line'] == 1
    assert secret not in json.dumps(failed)


def test_known_settings_and_profile_secrets_redacted():
    settings={'OANDA_ACCESS_TOKEN':'test-token','broker_profiles_json':json.dumps([{'api_secret':'profile-secret','account_id':'private-account'}])}
    result=_redact({'test-token':'message test-token', 'nested':['profile-secret','private-account']},settings)
    assert result == {'[redacted]':'message [redacted]','nested':['[redacted]','[redacted]']}


def test_workspace_backtest_uses_common_engine_cache_and_saved_runs(workspace,tmp_path):
    settings=Settings(_env_file=None,LEDGER_DATA_DIR=tmp_path/'data',ALPACA_API_KEY='test-key',
        ALPACA_API_SECRET='test-secret',ALPACA_DATA_BASE_URL='http://127.0.0.1:1',
        ALPACA_TRADING_BASE_URL='http://127.0.0.1:1')
    db=Database(settings.database_path);db.initialize()
    frames=pd.DataFrame({'timestamp':pd.date_range('2026-01-05T14:30Z',periods=3,freq='5min'),
        'open':[100,100,100],'high':[100,100,102],'low':[100,100,100],'close':[100,100,102],'volume':[10]*3})
    MarketStore(settings.market_data_dir).write_bars('alpaca-sip-split','AAPL','5m',frames)
    MarketCacheRepository(db).extend('alpaca-sip-split','AAPL','5m',pd.Timestamp('2026-01-01',tz='UTC'),pd.Timestamp('2026-02-01',tz='UTC'))
    services=SimpleNamespace(settings=settings,backtest_runs=BacktestRunRepository(db))
    source=template().replace('        return None','''        if not getattr(self, "sent", False):
            self.sent = True
            return EntrySignal("long", 99, 102)
        return None''')
    result=workspace.execute('backtest','_workspace_my_strategy.py',source,trusted=True,services=services,
        payload={'symbols':['AAPL'],'start_date':'2026-01-05','end_date':'2026-01-05',
                 'primary_timeframe':'5m','sizing_mode':'quantity','risk_value':1,
                 'run_notes':'test-secret','strategy_params':{'private_value':'test-secret'}})
    assert result['ok'],result
    run=result['result'];trade=run['trades'][0]
    assert trade['entry_time'].startswith('2026-01-05T14:35')
    assert trade['net_pnl'] == 2 and trade['r_multiple'] == 2
    saved=services.backtest_runs.get(run['saved_run']['id'])
    assert saved['result']['workspace']['source_sha256'] == run['workspace']['source_sha256']
    assert 'test-secret' not in json.dumps(result)
    assert 'test-secret' not in json.dumps(saved)
    from app.backtesting.strategies import strategy_registry
    assert 'workspace_my_strategy' not in {s.key for s in strategy_registry.specs()}


def test_workspace_api_boundaries(workspace,tmp_path):
    app=FastAPI();app.include_router(router,prefix='/api')
    app.dependency_overrides[workspace_dependency]=lambda:workspace
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(settings=Settings(_env_file=None,LEDGER_DATA_DIR=tmp_path))
    draft={'filename':'_workspace_my_strategy.py','source':template()}
    with TestClient(app) as client:
        assert client.get('/api/strategy-workspace/files').status_code == 200
        assert client.put('/api/strategy-workspace/files',json=draft).json()['ok']
        assert client.post('/api/strategy-workspace/syntax',json=draft).json()['ok']
        assert client.post('/api/strategy-workspace/execute',json={**draft,'action':'interface'}).status_code == 400
        assert client.post('/api/strategy-workspace/execute',json={**draft,'action':'interface','trusted':True}).json()['ok']
        assert client.put('/api/strategy-workspace/files',json=draft,headers={'origin':'https://evil.invalid'}).status_code == 403
    with TestClient(app,client=('192.0.2.1',1234)) as client:
        assert client.get('/api/strategy-workspace/files').status_code == 403

def test_activation_unique_discoverable_and_deactivation_preserves_history(workspace):
    from app.backtesting.strategies import strategy_registry
    source=template('activation_case');filename='_workspace_activation_case.py'
    workspace.save(filename,source)
    result=workspace.activate(filename,source,trusted=True)
    assert result['ok'],result
    try:
        strategy=strategy_registry.create('workspace_activation_case')
        assert strategy.workspace_provenance['source_sha256']==result['activation']['source_sha256']
        assert (workspace.root/'workspace_activation_case.py').exists()
        with pytest.raises(ValueError,match='already exists'):workspace.activate(filename,source,trusted=True)
        with pytest.raises(ValueError):workspace.deactivate('_workspace_unowned.py')
    finally:workspace.deactivate(filename)
    assert 'workspace_activation_case' not in {s.key for s in strategy_registry.specs()}
    assert workspace.read(filename)['source']==source
    assert (workspace.root/'_workspace_history'/f"{result['activation']['source_sha256']}.py").read_text()==source
    assert not workspace.list()['activations'][filename]['active']


def test_activation_requires_saved_exact_source_and_passing_tests(workspace):
    source=template('activation_bad')+'\ndef test_fails():\n    assert False\n'
    filename='_workspace_activation_bad.py';workspace.save(filename,source)
    with pytest.raises(ValueError,match='acknowledgement'):workspace.activate(filename,source)
    with pytest.raises(ValueError,match='exact source'):workspace.activate(filename,source+'\n',trusted=True)
    assert not workspace.activate(filename,source,trusted=True)['ok']
    assert not (workspace.root/'workspace_activation_bad.py').exists()


def test_active_workspace_can_be_revalidated_in_disposable_worker(workspace):
    from app.backtesting.strategies import strategy_registry
    from app.backtesting.workspace_worker import execute
    source=template('active_revalidate');filename='_workspace_active_revalidate.py'
    workspace.save(filename,source);assert workspace.activate(filename,source,trusted=True)['ok']
    active=strategy_registry._items['workspace_active_revalidate']
    try:
        result=execute({'key':'workspace_active_revalidate','filename':filename,'source':source,'action':'tests'})
        assert result['ok']
    finally:
        strategy_registry._items['workspace_active_revalidate']=active
        workspace.deactivate(filename)
