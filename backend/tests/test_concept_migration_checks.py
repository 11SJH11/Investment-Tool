"""Scoped equivalence probes, not authorization to migrate frozen strategy policies."""
from time import perf_counter
import pandas as pd
import numpy as np
import pytest
from app.market_concepts import registry
from app.market_concepts.base import ConceptRequest
from app.market_concepts.registry import ConceptRegistry,Definition
from app.market_concepts.builtins import swings,PivotParams
from tests.test_market_concepts import bars


def test_strict_pivot_values_match_amn_helper_on_completed_prefixes():
    from app.backtesting.strategies.amn_structure_retest_research_v1 import _confirmed_pivots
    frame=bars()
    for size in range(1,len(frame)+1):
        prefix=frame.iloc[:size]
        output=registry.evaluate(ConceptRequest(key='swing.strict.v1'),prefix,symbol='TEST',decision_time=prefix.timestamp.iloc[-1]+pd.Timedelta(minutes=1))['observations']
        for side in ('high','low'):
            expected=_confirmed_pivots(prefix,side,2,2)
            actual=[o for o in output if o.label=='swing_'+side]
            assert [(o.occurred_at,o.value) for o in actual]==[(p.time,p.price) for p in expected]


def test_vwap_matches_v4_helper_only_with_same_single_session_input():
    from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import _vwap
    frame=bars()
    for size in range(1,len(frame)+1):
        prefix=frame.iloc[:size]
        output=registry.evaluate(ConceptRequest(key='session_vwap.new_york.v1'),prefix,symbol='TEST',decision_time=prefix.timestamp.iloc[-1]+pd.Timedelta(minutes=1))['observations']
        assert output[-1].value==pytest.approx(_vwap(prefix),rel=1e-12)


@pytest.mark.parametrize('timeframe,minutes',[('1m',1),('5m',5),('15m',15),('30m',30),('1h',60),('4h',240),('1d',1440)])
def test_pivot_confirmation_is_causal_across_timeframes(timeframe,minutes):
    frame=bars();frame['timestamp']=pd.date_range('2026-01-02T14:30Z',periods=len(frame),freq=f'{minutes}min')
    frame['available_at']=frame.timestamp+pd.Timedelta(minutes=minutes)
    known=frame.available_at.iloc[4]
    before=registry.evaluate(ConceptRequest(key='swing.strict.v1',timeframe=timeframe),frame,symbol='TEST',decision_time=known-pd.Timedelta(microseconds=1))['observations']
    after=registry.evaluate(ConceptRequest(key='swing.strict.v1',timeframe=timeframe),frame,symbol='TEST',decision_time=known)['observations']
    assert len(after)>len(before)
    assert all(o.confirmed_at<=known for o in after)


@pytest.mark.parametrize('size',[50,500,2000])
def test_concept_cache_measurement_avoids_detector_reexecution(size):
    frame=pd.DataFrame({'timestamp':pd.date_range('2026-01-02T14:30Z',periods=size,freq='1min')})
    close=100+np.sin(np.arange(size)/5)
    frame=frame.assign(open=close,high=close+.1,low=close-.1,close=close,volume=100.)
    calls=[]
    def measured(frame,params,dependencies):calls.append(len(frame));return swings(frame,params,dependencies)
    local=ConceptRegistry();local.register(Definition('benchmark.strict.v1','Fixture',measured,PivotParams))
    request=ConceptRequest(key='benchmark.strict.v1');end=frame.timestamp.iloc[-1]+pd.Timedelta(minutes=1)
    start=perf_counter();first=local.evaluate(request,frame,symbol='TEST',decision_time=end);cold=perf_counter()-start
    start=perf_counter();second=local.evaluate(request,frame,symbol='TEST',decision_time=end);warm=perf_counter()-start
    assert first==second and calls==[size]
    print(f'concept-cache bars={size} cold_seconds={cold:.6f} warm_seconds={warm:.6f}')
