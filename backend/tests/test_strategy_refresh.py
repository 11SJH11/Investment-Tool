from copy import deepcopy
import pickle
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies._refresh import RefreshBusy
from app.api.dependencies import get_services
from app.api.strategy_lab import router
from app.services.backtest import BacktestService
from tests.test_research_infrastructure import services, base


def source(key='refresh_fixture', value=1):
    return f'''from app.backtesting.strategies.base import Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
VALUE = {value}
@strategy_registry.register
class Fixture(Strategy):
    spec = StrategySpec(key={key!r},name='Refresh fixture',timeframes=('1m',))
    def reset(self): self.marker = VALUE
    def on_bar(self,ctx): return None
'''


@pytest.fixture
def directory(tmp_path):
    registry = strategy_registry
    original_sources = registry.sources()
    original_root = registry._root
    folder=tmp_path/'strategies';folder.mkdir()
    for filename,content in original_sources.items():
        (folder/filename).write_bytes(content)
    registry._root=folder
    try:
        yield folder
    finally:
        registry._root=original_root
        assert registry.refresh(sources=original_sources)['ok']


def test_discover_update_preserves_old_instances_and_existing_strategies(directory):
    before={s.key for s in strategy_registry.specs()}
    path=directory/'refresh_fixture.py';path.write_text(source(),encoding='utf-8')
    outcome=strategy_registry.refresh()
    assert outcome['ok'] and outcome['added']==1 and outcome['updated']==0
    assert before < {s.key for s in strategy_registry.specs()}
    old=strategy_registry.create('refresh_fixture');old.reset();assert old.marker==1
    original_hash=strategy_registry.provenance('refresh_fixture')['source_sha256']
    # Same length edits within the same timestamp tick must bypass .pyc caches.
    path.write_text(source(value=2),encoding='utf-8')
    outcome=strategy_registry.refresh()
    assert outcome['ok'] and outcome['updated']==1 and outcome['added']==0
    new=strategy_registry.create('refresh_fixture');new.reset();assert new.marker==2
    old.reset();assert old.marker==1
    assert strategy_registry.provenance('refresh_fixture')['source_sha256']!=original_hash
    assert strategy_registry.refresh()['updated']==0


@pytest.mark.parametrize('broken,expected',[
    ('def broken(:','SyntaxError'),
    ('import ledger_nonexistent_fixture_dependency','missing module'),
    (source(key='sma_cross'), 'already registered'),
    (source().replace("StrategySpec(key='refresh_fixture',name='Refresh fixture',timeframes=('1m',))",'None'),'StrategySpec'),
    (source().replace('def on_bar(self,ctx)', 'def on_bar(self)'), 'Invalid strategy'),
])
def test_bad_module_rolls_back_registry_and_module_globals(directory,broken,expected):
    # Use a real existing key for the duplicate fixture, independent of names.
    if expected=='already registered':broken=source(key=strategy_registry.specs()[0].key)
    before=dict(strategy_registry._items);provenance={k:strategy_registry.provenance(k) for k in before}
    (directory/'bad_fixture.py').write_text(broken,encoding='utf-8')
    outcome=strategy_registry.refresh()
    assert not outcome['ok']
    assert any(e['module']=='bad_fixture.py' and expected in e['message'] for e in outcome['errors'])
    assert strategy_registry._items==before
    assert {k:strategy_registry.provenance(k) for k in before}==provenance
    assert 'app.backtesting.strategies.bad_fixture' not in sys.modules


def test_active_execution_rejects_refresh_and_api_returns_current_list(directory):
    app=FastAPI();app.include_router(router)
    app.dependency_overrides[get_services]=lambda:SimpleNamespace(backtest=BacktestService(None))
    path=directory/'refresh_fixture.py';path.write_text(source(),encoding='utf-8')
    with TestClient(app) as client:
        with strategy_registry.executing():
            response=client.post('/strategy-lab/strategies/refresh')
            assert response.status_code==409 and 'Wait for active' in response.json()['detail']
        response=client.post('/strategy-lab/strategies/refresh').json()
        assert response['ok'] and response['added']==1
        assert any(s['key']=='refresh_fixture' for s in response['strategies'])
        path.write_text('broken syntax !',encoding='utf-8')
        response=client.post('/strategy-lab/strategies/refresh').json()
        assert not response['ok'] and response['errors']
        assert any(s['key']=='refresh_fixture' for s in response['strategies'])


def test_saved_runs_are_immutable_and_future_runs_record_new_hash(directory,tmp_path):
    path=directory/'refresh_fixture.py';path.write_text(source(),encoding='utf-8');assert strategy_registry.refresh()['ok']
    service,_,_=services(tmp_path/'store')
    payload={**base(),'strategy_key':'refresh_fixture','save_run':True}
    first=service.run(payload);saved=service.get_run(first['saved_run']['id']);before=deepcopy(saved)
    path.write_text(source(value=2),encoding='utf-8');assert strategy_registry.refresh()['ok']
    second=service.run(payload)
    assert service.get_run(saved['id'])==before
    assert first['strategy']['implementation']['source_sha256']!=second['strategy']['implementation']['source_sha256']
    assert saved['config']['strategy_provenance']==first['strategy']['implementation']


def test_worker_uses_captured_source_not_later_disk_changes(directory,tmp_path):
    from app import research_runtime
    path=directory/'refresh_fixture.py';path.write_text(source(),encoding='utf-8');assert strategy_registry.refresh()['ok']
    captured=strategy_registry.sources()
    path.write_text(source(value=8),encoding='utf-8')
    snapshot=tmp_path/'inputs.pickle';snapshot.write_bytes(pickle.dumps({'strategy_sources':captured}))
    previous=research_runtime._inputs
    try:
        research_runtime.initialize_worker(snapshot,None)
        instance=strategy_registry.create('refresh_fixture');instance.reset()
        assert instance.marker==1
    finally:research_runtime._inputs=previous
