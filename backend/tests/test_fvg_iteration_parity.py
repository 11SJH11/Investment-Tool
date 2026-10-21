import random

import pandas as pd
import pytest

from app.market_concepts.base import Observation
from app.market_concepts.builtins import gaps


def original(frame, params):
    output=[]
    for i in range(2,len(frame)):
        a,c=frame.iloc[i-2],frame.iloc[i]
        if c.low>a.high:lower,upper,label=float(a.high),float(c.low),'bullish_fvg'
        elif c.high<a.low:lower,upper,label=float(c.high),float(a.low),'bearish_fvg'
        else:continue
        if a.close<=0 or (upper-lower)/a.close*10000<params['minimum_bps']:continue
        output.append(Observation(kind='zone',label=label,occurred_at=c.timestamp,
                                  confirmed_at=c.available_at,lower=lower,upper=upper))
    return output


def frame(size):
    rng=random.Random(87)
    close=[rng.choice([0.,-1.,2990.,3000.,3010.,3020.]) for _ in range(size)]
    stamps=pd.date_range('2026-03-07',periods=size,freq='15min',tz='UTC')
    return pd.DataFrame(dict(timestamp=stamps,available_at=stamps+pd.Timedelta(minutes=15),
        open=close,close=close,high=[v+1 for v in close],low=[v-1 for v in close],volume=100))


@pytest.mark.parametrize('size',[0,1,2,3,30,500])
@pytest.mark.parametrize('minimum_bps',[0.,1.,10.,10000.])
def test_exact_observation_parity(size,minimum_bps):
    data=frame(size);params=dict(minimum_bps=minimum_bps)
    assert gaps(data,params,{})==original(data,params)


def test_every_prefix_and_future_changes_preserve_causal_output():
    data=frame(70);params=dict(minimum_bps=0.)
    for n in range(len(data)+1):
        assert gaps(data.iloc[:n],params,{})==original(data.iloc[:n],params)
    before=gaps(data.iloc[:40],params,{})
    data.loc[40:,'high']=999999.
    data.loc[40:,'low']=-999999.
    assert gaps(data.iloc[:40],params,{})==before


def test_non_default_index_and_input_not_mutated():
    data=frame(30);data.index=range(100,130)
    before=data.copy(deep=True);params=dict(minimum_bps=1.)
    assert gaps(data,params,{})==original(data,params)
    pd.testing.assert_frame_equal(data,before)
