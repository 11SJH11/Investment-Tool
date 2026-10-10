"""Initial narrow definitions; no strategy-specific entry/exit decisions."""
import inspect
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from app.indicators.builtins import VWAP
from .base import Observation
from .registry import Definition, registry

class NoParams(BaseModel):
    model_config=ConfigDict(extra='forbid')
class PivotParams(NoParams):
    left: int=Field(default=2,ge=1,le=50,strict=True)
    right: int=Field(default=2,ge=1,le=50,strict=True)
class GapParams(NoParams):
    minimum_bps: float=Field(default=0,ge=0,le=10000,allow_inf_nan=False)

def vwap(frame,params,dependencies):
    if frame.empty:return []
    values=VWAP().calculate(frame)
    return [Observation(kind='series',label='Session VWAP',occurred_at=row.timestamp,confirmed_at=row.available_at,value=float(values.iloc[i]))
            for i,row in enumerate(frame.itertuples()) if pd.notna(values.iloc[i])]

def swings(frame,params,dependencies):
    output=[];left=params['left'];right=params['right']
    for i in range(left,len(frame)-right):
        row=frame.iloc[i];window=frame.iloc[i-left:i+right+1]
        for column,label,extreme in [('high','swing_high',window.high.max()),('low','swing_low',window.low.min())]:
            # Strict extrema: ties produce no pivot. Confirmation is the rightmost bar's completion.
            if row[column]==extreme and (window[column]==extreme).sum()==1:
                output.append(Observation(kind='point',label=label,occurred_at=row.timestamp,
                    confirmed_at=frame.iloc[i+right].available_at,value=float(extreme)))
    return output

def structure(frame,params,dependencies):
    last={};output=[]
    for pivot in dependencies['swing.strict.v1']:
        prior=last.get(pivot.label);last[pivot.label]=pivot.value
        if prior is None:continue
        label=('HH' if pivot.value>prior else 'LH' if pivot.value<prior else 'EH') if pivot.label=='swing_high' else ('HL' if pivot.value>prior else 'LL' if pivot.value<prior else 'EL')
        output.append(pivot.model_copy(update={'label':label,'kind':'state'}))
    return output

def gaps(frame,params,dependencies):
    output=[]
    for i in range(2,len(frame)):
        a,c=frame.iloc[i-2],frame.iloc[i]
        if c.low>a.high:lower,upper,label=float(a.high),float(c.low),'bullish_fvg'
        elif c.high<a.low:lower,upper,label=float(c.high),float(a.low),'bearish_fvg'
        else:continue
        if a.close<=0 or (upper-lower)/a.close*10000<params['minimum_bps']:continue
        output.append(Observation(kind='zone',label=label,occurred_at=c.timestamp,confirmed_at=c.available_at,lower=lower,upper=upper))
    return output

registry.register(Definition('session_vwap.new_york.v1','HLC3 volume-weighted running mean, reset by New York calendar date; same canonical VWAP indicator.',vwap,NoParams,
    implementation_files=(inspect.getsourcefile(VWAP),),limitations='Uses supplied session-filtered bars. Not a CME evening-session VWAP. Zero cumulative volume is unavailable.'))
registry.register(Definition('swing.strict.v1','Unique strict N-left/N-right high/low; ties rejected. Known only when the rightmost bar completes.',swings,PivotParams))
registry.register(Definition('structure.strict.v1','HH/LH/EH and HL/LL/EL comparisons between successive confirmed 2/2 strict pivots.',structure,NoParams,('swing.strict.v1',)))
registry.register(Definition('fvg.three_candle.v1','Bullish: current low > high two bars earlier; bearish mirror. Confirmed at third candle close. Bps size uses first candle close.',gaps,GapParams,
    limitations='Detection-only immutable zone. No displacement, mitigation, invalidation or profitability claim. May span sessions when input does.'))
