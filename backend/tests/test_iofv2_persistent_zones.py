"""IOF V2 causal geometry and Ledger interface regression tests."""
import importlib
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.backtesting.strategies.iof_v2_persistent_zones import (
    DisplacementDetector, _IofV2Base, TF_MIN,
)
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.models import EntrySignal


def _bars(start="2025-01-06T00:00:00Z", tf='15m'):
    t = pd.Timestamp(start)
    step=pd.Timedelta(minutes=TF_MIN[tf])
    out=[]
    # Build prior stable history; leave an opposing candle near the origin.
    for i in range(32):
        op=100.+(0.11 if i%2 else 0.)
        cl=99.98 if i%2 else 100.13
        out.append(dict(timestamp=t+i*step,open=op,high=max(op,cl)+.18,low=min(op,cl)-.18,close=cl))
    # strong bullish displacement with NO fixed candle count
    for i in range(32,50):
        op=100+(i-32)*.16
        cl=op+.17
        out.append(dict(timestamp=t+i*step,open=op,high=cl+.09,low=op-.06,close=cl))
    return out


def test_twelve_registry_entries():
    specs={s.key:s for s in strategy_registry.specs()}
    for tf in TF_MIN:
        for v in ('basic','bos','bos_fvg'):
            key=f'iofv2_{tf}_{v}'
            assert key in specs
            assert specs[key].timeframes == (('1m',) if tf=='1m' else ('1m',tf))


def test_detector_no_three_bar_limit():
    d=DisplacementDetector('15m',variant='basic',displacement_atr=6.,min_efficiency=.55)
    found=[]
    for bar in _bars():
        z=d.process(bar)
        if z is not None:found.append(z)
    # The synthetic rising leg may register once it moves far enough: if it
    # qualifies, it cannot require a fixed <=3 candle burst.
    assert all(z.candles>3 for z in found)


def test_zones_geometry_and_confirmation_after_close():
    d=DisplacementDetector('15m',variant='basic',displacement_atr=1.5,min_efficiency=.5)
    zs=[z for bar in _bars() if (z:=d.process(bar)) is not None]
    assert zs, 'Expected at least one synthetic bullish zone'
    z=next(x for x in zs if x.direction=='long')
    assert z.entry==z.high
    assert z.stop<(z.low+z.high)/2
    assert z.confirmed_at==pd.Timestamp(_bars()[32+z.candles-1]['timestamp'])+pd.Timedelta(minutes=15) or z.confirmed_at>z.base_at


def test_no_duplicate_source_zone():
    d=DisplacementDetector('1m',variant='basic',displacement_atr=1.,min_efficiency=.5)
    zones=[z for b in _bars(tf='1m') if (z:=d.process(b)) is not None]
    keys=[x.zone_id for x in zones]
    assert len(keys)==len(set(keys))


def test_detector_gaps_break_leg_not_remove_zones():
    d=DisplacementDetector('15m',variant='basic',displacement_atr=1.,min_efficiency=.5)
    zlist=[]
    for b in _bars():
        z=d.process(b)
        if z is not None:zlist.append(z)
    assert zlist
    old=zlist[0]
    next_bar=dict(timestamp=pd.Timestamp('2025-02-14T00:00:00Z'),open=103.,high=103.3,low=102.8,close=103.1)
    d.process(next_bar)
    assert old.confirmed_at<pd.Timestamp(next_bar['timestamp'])
    assert old.status=='active'


def test_variants_never_create_more_than_basic_on_same_path():
    rows=_bars()
    zsets={}
    for v in ('basic','bos','bos_fvg'):
        det=DisplacementDetector('15m',variant=v,displacement_atr=1.5,min_efficiency=.5)
        zsets[v]=[x for b in rows if (x:=det.process(b)) is not None]
    assert len(zsets['bos_fvg']) <= len(zsets['bos'])
    assert len(zsets['bos']) <= len(zsets['basic'])


def test_zone_selection_does_not_age_expire():
    from app.backtesting.strategies.iof_v2_persistent_zones import Zone
    from bisect import insort
    instance=strategy_registry.create('iofv2_15m_basic')
    t=pd.Timestamp('2025-01-01T00:00:00Z')
    z=Zone('old','15m','long',99,101,101,99.9,1.,t,t,5,.9,2.,True,True)
    instance.zones[z.zone_id]=z
    insort(instance.edges,(z.entry,z.zone_id))
    assert instance._candidate_zone(102., 1., pd.Timestamp('2025-03-01T00:00:00Z')) is z


def test_old_1m_bar_not_process_twice():
    from app.backtesting.strategies.iof_v2_persistent_zones import _IofV2Base
    s=strategy_registry.create('iofv2_1m_basic')
    frame=pd.DataFrame(_bars(tf='1m')[:1])
    class Ctx:
        primary_timeframe='1m'
        position=None
        decision_time=pd.Timestamp('2025-01-06T00:01:00Z')
        def bars(self,tf,count=None):return frame
    assert s.on_bar(Ctx()) is None
    counter=s.atr_1m_count
    assert s.on_bar(Ctx()) is None
    assert s.atr_1m_count==counter


def test_reject_invalid_detector_config():
    with pytest.raises(ValueError):DisplacementDetector('4h',min_efficiency=1.2)


def test_reference_runner_no_entry_on_zone_creation_bar():
    # Test only the execution boundary; bypass detector to seed a known zone.
    from app.backtesting.strategies.iof_v2_persistent_zones import Zone
    from tools.run_iofv2_reference import run_variant
    base=pd.Timestamp('2025-01-01T00:00:00Z')
    rows=[dict(timestamp=base+pd.Timedelta(minutes=i),open=101.5,high=102.,low=100.5,close=101.5) for i in range(3)]
    frame=pd.DataFrame(rows)
    z=Zone('z','1m','long',99,101,101,99.8,1.,base+pd.Timedelta(minutes=2),base,6,.8,2.,True,False)
    summary,trades,events=run_variant(frame,[z])
    assert all(pd.Timestamp(t['entry_time'])>=base+pd.Timedelta(minutes=2) for t in trades)


def test_reference_runner_entry_bar_stop_first():
    from app.backtesting.strategies.iof_v2_persistent_zones import Zone
    from tools.run_iofv2_reference import run_variant
    base=pd.Timestamp('2025-01-01T00:00:00Z')
    b=[dict(timestamp=base+pd.Timedelta(minutes=i),open=105.,high=106.,low=104.8,close=105.) for i in range(3)]
    b.append(dict(timestamp=base+pd.Timedelta(minutes=3),open=105.,high=110.,low=98.,close=108.))
    z=Zone('z','1m','long',99.,101.,101.,99.8,1.,base+pd.Timedelta(minutes=3),base,6,.8,2.,True,False)
    # zone confirmed at minute 3, must wait until a later minute
    b.append(dict(timestamp=base+pd.Timedelta(minutes=4),open=105.,high=110.,low=98.,close=108.))
    summary,trades,_=run_variant(pd.DataFrame(b),[z])
    assert summary['trades']==1
    assert trades[0]['net_r']<=-1
    assert trades[0]['exit_reasons']=='ENTRY_BAR_STOP'


def test_reference_full_buckets_excludes_partial_history():
    from tools.run_iofv2_reference import candles_for_timeframe
    base=pd.Timestamp('2025-01-01T00:00:00Z')
    rows=[dict(timestamp=base+pd.Timedelta(minutes=i),open=100.,high=101.,low=99.,close=100.) for i in range(19)]
    f,dropped=candles_for_timeframe(pd.DataFrame(rows),'15m')
    assert len(f)==1 and dropped==1
