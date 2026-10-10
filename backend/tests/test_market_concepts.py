from dataclasses import replace
from copy import deepcopy
import pandas as pd
import pytest
from app.market_concepts import registry
from app.market_concepts.registry import ConceptRegistry, Definition
from app.market_concepts.builtins import NoParams, vwap
from app.backtesting.context import StrategyContext
from app.indicators.builtins import VWAP


def bars():
    frame=pd.DataFrame({'timestamp':pd.date_range('2026-01-02T14:30Z',periods=7,freq='min'),
        'open':[2,3,5,3,2,4,5],'high':[3,4,6,4,3,5,6],'low':[1,2,4,2,1,3,4],
        'close':[2,3,5,3,2,4,5],'volume':[10]*7})
    return frame

def calc(key,frame=None,when='2026-01-02T15:00Z',**params):
    return registry.evaluate({'key':key,'params':params},bars() if frame is None else frame,symbol='TEST',decision_time=pd.Timestamp(when))

def test_swing_right_confirmation_and_future_mutation():
    early=calc('swing.strict.v1',when='2026-01-02T14:34Z')
    assert not early['observations']
    confirmed=calc('swing.strict.v1',when='2026-01-02T14:35Z')['observations'][0]
    assert confirmed.label=='swing_high' and confirmed.occurred_at==pd.Timestamp('2026-01-02T14:32Z')
    assert confirmed.confirmed_at==pd.Timestamp('2026-01-02T14:35Z')
    changed=bars();changed.loc[5:,'high']=999
    assert calc('swing.strict.v1',changed,when='2026-01-02T14:35Z')==calc('swing.strict.v1',when='2026-01-02T14:35Z')

def test_no_incomplete_htf_and_declared_versions_only():
    frame=bars().iloc[:3].copy();frame['available_at']=pd.date_range('2026-01-02T14:45Z',periods=3,freq='15min')
    ctx=StrategyContext(symbol='TEST',primary_timeframe='15m',decision_time=pd.Timestamp('2026-01-02T14:44Z'),frames={'15m':frame},position=None,equity=1,
        concepts={'vwap':{'key':'session_vwap.new_york.v1','timeframe':'15m'}})
    assert not ctx.concept('vwap')['observations']
    with pytest.raises(ValueError):ctx.concept('undeclared')
    ctx.decision_time=pd.Timestamp('2026-01-02T14:45Z')
    assert len(ctx.concept('vwap')['observations'])==1

def test_vwap_matches_canonical_indicator_and_output_isolation():
    result=calc('session_vwap.new_york.v1')
    assert [x.value for x in result['observations']]==VWAP().calculate(bars()).tolist()
    result['provenance']['params']['fake']=123
    assert 'fake' not in calc('session_vwap.new_york.v1')['provenance']['params']

def test_zone_confirmation_and_no_retroactive_updates():
    result=calc('fvg.three_candle.v1',when='2026-01-02T14:33Z')
    zone=result['observations'][0]
    assert zone.lower==3 and zone.upper==4 and zone.confirmed_at==pd.Timestamp('2026-01-02T14:33Z')
    assert zone in calc('fvg.three_candle.v1')['observations']

def test_cache_identity_includes_data_params_symbol_and_source(tmp_path):
    first=calc('swing.strict.v1');changed=bars();changed['provider']='fixture-new'
    assert first['cache_key']!=calc('swing.strict.v1',changed)['cache_key']
    assert first['cache_key']!=calc('swing.strict.v1',right=1)['cache_key']
    assert first['cache_key']!=registry.evaluate({'key':'swing.strict.v1'},bars(),symbol='OTHER',decision_time=pd.Timestamp('2026-01-02T15:00Z'))['cache_key']
    local=ConceptRegistry();source=tmp_path/'implementation.py';source.write_text('v1')
    local.register(Definition('test.profile.v1','fixture',vwap,NoParams,implementation_files=(str(source),)))
    before=local.provenance({'key':'test.profile.v1'});source.write_text('v2')
    assert before['source_sha']!=local.provenance({'key':'test.profile.v1'})['source_sha']

def test_exact_versions_cycles_and_private_scope():
    local=ConceptRegistry();one=Definition('test.profile.v1','fixture',vwap,NoParams)
    local.register(one);local.register(replace(one,key='test.profile.v2'))
    with pytest.raises(ValueError):local.register(one)
    with pytest.raises(ValueError):local.provenance({'key':'test.profile.v3'})
    local.register(replace(one,key='strategy-local:test.profile.v1'))
    assert local.provenance({'key':'strategy-local:test.profile.v1'})['scope']=='strategy-local'
    local.register(replace(one,key='a.profile.v1',dependencies=('b.profile.v1',)))
    with pytest.raises(ValueError,match='Circular'):local.register(replace(one,key='b.profile.v1',dependencies=('a.profile.v1',)))
    assert registry.provenance({'key':'structure.strict.v1'})['dependencies'][0]['key']=='swing.strict.v1'

def test_engine_control_parity_and_saved_provenance(tmp_path,monkeypatch):
    from app.backtesting.strategies import strategy_registry
    from app.services.backtest import BacktestService
    from app.storage.database import Database
    from app.storage.backtest_run_repository import BacktestRunRepository
    from tests.test_phase52_saved_runs_and_chart_series import HoldToEnd
    class Observing(HoldToEnd):
        spec=replace(HoldToEnd.spec,key='concept_fixture',concepts={'vwap':{'key':'session_vwap.new_york.v1','timeframe':'1m'}})
        def on_bar(self,ctx):
            ctx.concept('vwap')
            return super().on_bar(ctx)
    monkeypatch.setitem(strategy_registry._items,'concept_fixture',Observing)
    db=Database(tmp_path/'db');db.initialize();service=BacktestService(None,BacktestRunRepository(db))
    inputs=dict(strategy_key='concept_fixture',symbols=['AAPL'],primary='1m',additional=[],session='regular',requested_session='regular',
        start=pd.Timestamp('2026-01-02T14:30Z'),end=pd.Timestamp('2026-01-02T14:37Z'),delay=0,
        frames_by_symbol={'AAPL':{'1m':bars()}},diagnostic_history={},diagnostic_warnings=[],providers={})
    result=service.run({'strategy_key':'concept_fixture'},prepared=inputs)
    saved=service.runs.get(result['saved_run']['id'])
    assert saved['result']['strategy']['concepts']['vwap']['key']=='session_vwap.new_york.v1'
    before=deepcopy(saved['result'])
    assert service.runs.get(result['saved_run']['id'])['result']==before
    from app.backtesting.engine import BacktestEngine
    from app.backtesting.models import BacktestConfig
    engine=BacktestEngine(BacktestConfig())
    a=engine.run(symbol_frames={'AAPL':{'1m':bars()}},strategies={'AAPL':HoldToEnd()},primary_timeframe='1m')
    b=engine.run(symbol_frames={'AAPL':{'1m':bars()}},strategies={'AAPL':Observing()},primary_timeframe='1m')
    assert a['trades']==b['trades'] and a['metrics']==b['metrics']
