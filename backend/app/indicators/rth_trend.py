"""Review adapter to the reference strategy's canonical completed-RTH math.

This does not substitute provider daily bars or duplicate its EMA/resampling.
Imports are delayed to avoid indicator/strategy discovery cycles.
"""
import pandas as pd
from app.indicators.base import Indicator, IndicatorSpec
from app.indicators.registry import indicator_registry

@indicator_registry.register
class RthTrendEMA(Indicator):
    spec=IndicatorSpec(key='rth_trend_ema',name='Completed RTH regime EMA',causal=True,defaults={'length':20,'timeframe':'1d'})

    def calculate(self,bars,**params):
        from app.backtesting.context import StrategyContext,completion_indexes
        from app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 import VwapTrendEntryExitDistanceResearchV4,_trend_cache_key
        timeframe=params.get('timeframe','1d');length=int(params.get('length',20))
        strategy=VwapTrendEntryExitDistanceResearchV4(trend_timeframe=timeframe,trend_ema_length=length)
        strategy.reset()
        frames={'1m':bars};indexes=completion_indexes(frames)
        previous=object();value=None;values=[]
        for decision in indexes['1m']:
            key=_trend_cache_key(decision.to_pydatetime(),timeframe)
            if key!=previous:
                ctx=StrategyContext(symbol='REVIEW',primary_timeframe='1m',decision_time=decision.to_pydatetime(),frames=frames,position=None,equity=0,completion_indexes=indexes)
                _,_,value=strategy._trend_state(ctx)
                previous=key
            values.append(value)
        return pd.Series(values,index=bars.index,dtype=float)
