"""Bounded descriptive concept benchmarks. Follow-up observations are research only."""
from collections import Counter
from hashlib import sha256
from statistics import mean, median
import pandas as pd
from zoneinfo import ZoneInfo
from app.backtesting.context import timeframe_delta
from . import registry

MAX_BARS = 2000


def summary(values):
    return {'n':len(values),'mean':mean(values) if values else None,'median':median(values) if values else None,
            'min':min(values) if values else None,'max':max(values) if values else None}


def benchmark(request, bars, symbol, horizon=20):
    if not 1<=horizon<=100:raise ValueError('Use a follow-up horizon of 1 to 100 bars')
    if not 1<=len(bars)<=MAX_BARS:raise ValueError('Concept audits require 1 to 2000 prepared bars; use a smaller declared development baseline')
    frame=bars.copy().reset_index(drop=True)
    frame['timestamp']=pd.to_datetime(frame.timestamp,utc=True)
    if 'available_at' not in frame:frame['available_at']=frame.timestamp+timeframe_delta(request.timeframe)
    frame['available_at']=pd.to_datetime(frame.available_at,utc=True)
    last=frame.available_at.max()
    if pd.isna(last):raise ValueError('Concept completion times are unavailable')
    output=registry.evaluate(request,frame,symbol=symbol,decision_time=last)
    observations=output['observations']
    if len(observations)>10000:raise ValueError('Concept audit observation limit exceeded')
    # Sample deterministic chronological prefixes; this is a regression probe, not formal proof.
    cutoffs=sorted(set(frame.available_at))
    indexes=sorted({round(i*(len(cutoffs)-1)/min(7,len(cutoffs)-1)) for i in range(min(8,len(cutoffs)))}) if len(cutoffs)>1 else [0]
    probes=[]
    for index in indexes:
        cutoff=cutoffs[index]
        actual=registry.evaluate(request,frame,symbol=symbol,decision_time=cutoff)['observations']
        expected=tuple(o for o in observations if o.confirmed_at<=cutoff)
        probes.append({'at':cutoff.isoformat(),'observations':len(actual),'matches_final_history':actual==expected})
    lags=[(o.confirmed_at-o.occurred_at).total_seconds() for o in observations]
    sizes=[(o.upper-o.lower)/abs((o.upper+o.lower)/2)*10000 for o in observations if o.kind=='zone' and (o.upper+o.lower)!=0]
    by_day=Counter(o.confirmed_at.astimezone(ZoneInfo('America/New_York')).date().isoformat() for o in observations)
    details=[];up=[];down=[];touch=[];complete=0;censored=0
    for index,o in enumerate(observations):
        if o.kind=='series':continue
        start=int(frame.timestamp.searchsorted(pd.Timestamp(o.confirmed_at),side='left'))
        future=frame.iloc[start:start+horizon]
        full=len(future)==horizon
        complete+=full;censored+=not full
        reference=o.value if o.value is not None else (o.lower+o.upper)/2 if o.kind=='zone' else None
        item={'index':index,'complete_horizon':full,'available_followup_bars':len(future),'first_touch_bars':None}
        if o.kind=='zone':
            intersections=(future.low<=o.upper)&(future.high>=o.lower)
            if intersections.any():item['first_touch_bars']=int(next(i for i,x in enumerate(intersections) if x))+1
            if full and item['first_touch_bars'] is not None:touch.append(item['first_touch_bars'])
        if full and reference is not None and reference>0:
            u=(float(future.high.max())/reference-1)*10000
            d=(float(future.low.min())/reference-1)*10000
            up.append(u);down.append(d);item.update(upward_bps=u,downward_bps=d)
        details.append(item)
    eligible_zones=sum(o.kind=='zone' and details_by_index['complete_horizon'] for details_by_index in details for o in [observations[details_by_index['index']]])
    # Fixed hash sample plus zone size extremes; never select on subsequent profitability.
    selected=sorted(range(len(observations)),key=lambda i:sha256((output['cache_key']+':'+str(i)).encode()).hexdigest())[:6]
    zones=[i for i,o in enumerate(observations) if o.kind=='zone']
    if zones:
        ranked=sorted(zones,key=lambda i:(observations[i].upper-observations[i].lower,i));selected.extend([ranked[0],ranked[-1]])
    examples=[]
    for index in sorted(set(selected)):
        o=observations[index];center=int(frame.timestamp.searchsorted(pd.Timestamp(o.occurred_at)))
        end=int(frame.timestamp.searchsorted(pd.Timestamp(o.confirmed_at)))+horizon
        window=frame.iloc[max(0,center-12):min(len(frame),end+1)]
        rows=[{k:(r[k].isoformat() if k in {'timestamp','available_at'} else float(r[k])) for k in ('timestamp','available_at','open','high','low','close','volume')} for _,r in window.iterrows()]
        if o.kind=='series':
            values=[{'timestamp':x.confirmed_at.isoformat(),'value':x.value} for x in observations if x.kind=='series' and x.label==o.label and len(window) and window.timestamp.iloc[0]<=x.confirmed_at<=window.available_at.iloc[-1]]
            overlays=[{'label':o.label+' (at confirmation)','values':values}]
        else:
            levels=[('lower',o.lower),('upper',o.upper)] if o.kind=='zone' else [('value',o.value)]
            overlays=[{'label':o.label+' '+name+' (known after confirmation)','values':[{'timestamp':r['timestamp'],'value':v} for r in rows if pd.Timestamp(r['timestamp'])>=o.confirmed_at]} for name,v in levels if v is not None]
        examples.append({'index':index,'observation':o.model_dump(mode='json'),'bars':rows,'overlays':overlays,
                         'followup':next((x for x in details if x['index']==index),None)})
    return {'version':'concept_benchmark_v1','symbol':symbol,'timeframe':request.timeframe,'provenance':output['provenance'],
        'data_fingerprint':output['data_fingerprint'],'bar_count':len(frame),'observation_count':len(observations),
        'counts':dict(Counter(o.label for o in observations)),'confirmation_lag_seconds':summary(lags),
        'confirmation_day_counts':dict(sorted(by_day.items())),'zone_size_midpoint_bps':summary(sizes),
        'causality':{'status':'PASS' if all(p['matches_final_history'] for p in probes) else 'FAIL','probes':probes,'scope':'Up to eight completed-data prefix comparisons; not a proof for every possible input.'},
        'followup':{'horizon_bars':horizon,'complete_observations':complete,'right_censored_observations':censored,
            'upward_bps':summary(up),'downward_bps':summary(down),'complete_zones':eligible_zones,'touched_complete_zones':len(touch),'time_to_first_touch_bars':summary(touch)},
        'examples':examples,'sample_policy':'Six hash-selected observations plus smallest/largest raw-width zones, deduplicated. No outcome-based selection.',
        'limitations':['Follow-up uses bars starting at/after confirmation, never the confirming candle high/low. Research-only; never an entry feature.',
            'Excursion summaries use complete horizons and positive reference prices only; series excluded. Signs are raw price movements, not trade returns.',
            'Zone touch means OHLC intersects the bounds; no inferred fill, mitigation, invalidation or intrabar ordering.',
            'Calendar-day counts are New York confirmation dates, not exchange sessions. Samples are not profitability evidence.']}
