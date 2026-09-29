"""Offline NQ provenance fixture benchmark; not a live provider timing claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter

parser=argparse.ArgumentParser()
parser.add_argument('--app-root',default=str(Path(__file__).resolve().parents[1]))
parser.add_argument('--output',required=True)
args=parser.parse_args()
scratch=tempfile.TemporaryDirectory(prefix='ledger-nq-benchmark-',ignore_cleanup_errors=True)
os.environ['LEDGER_DATA_DIR']=scratch.name
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,args.app_root)
import pandas as pd
try:
    from app.performance import Profile
except ImportError:
    from app.services.performance import Profile
from app.services.backtest import BacktestService
from app.services.market_data import MarketDataService
from app.services.chart_data import prepare_chart_bars
from app.storage.market_store import MarketStore
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.backtest_run_repository import BacktestRunRepository
from tests.test_continuous_execution import provider, ROLL

root=Path(scratch.name);p=provider(root);original=p.http.handler
intraday=[]
for day in ['2026-06-09','2026-06-10','2026-06-11','2026-06-12']:
    ts=pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
    f=pd.DataFrame(dict(timestamp=ts,open=20100.,high=20101.,low=20099.,close=20100.,volume=100.))
    f.loc[15,['open','high','low','close']]=[20100,20103,20100,20102]
    f.loc[16,['open','high','low','close']]=[20103,20105,20102,20104]
    f.loc[17,['open','high','low','close']]=[20104,20112,20103,20111]
    intraday.append(f)
data=pd.concat(intraday,ignore_index=True)
def handler(url,params,headers):
    if url.endswith('/contracts') or params.get('resolution')=='1session':
        return original(url,params,headers)
    return {'results':[dict(window_start=r.timestamp.value,open=r.open,high=r.high,low=r.low,close=r.close,volume=r.volume)
                       for r in data.itertuples() if params['window_start.gte']<=r.timestamp.value<params['window_start.lt']]}
p.http.handler=handler
db=Database(root/'fixture.db');db.initialize()
market=MarketDataService(p,MarketStore(root/'market'),MarketCacheRepository(db))
service=BacktestService(market,BacktestRunRepository(db))
start=pd.Timestamp('2026-06-09T00:00Z').to_pydatetime();end=pd.Timestamp('2026-06-13T00:00Z').to_pydatetime()
output={'fixture':True,'bars':len(data),'measurements':[]}
def record(label,fn):
    calls=len(p.http.calls)
    with Profile() as profile:
        t=perf_counter();value=fn();elapsed=perf_counter()-t
    raw=value.to_json(date_format='iso',orient='split') if isinstance(value,pd.DataFrame) else json.dumps({k:value[k] for k in ('trades','metrics','setups')},sort_keys=True,default=str)
    row=dict(label=label,wall_seconds=elapsed,provider_calls=len(p.http.calls)-calls,digest=hashlib.sha256(raw.encode()).hexdigest(),**profile.snapshot())
    try:
        from app.frame_cache import frames
        row['cache']=frames.stats()
    except ImportError:pass
    output['measurements'].append(row)
    Path(args.output).write_text(json.dumps(output,indent=2),encoding='utf-8');print(json.dumps(row),flush=True)
record('chart_cold',lambda:prepare_chart_bars(market.get_bars('NQ1!','1m',start,end),'5m','24h',session_profile='futures_24h')[0])
record('chart_warm',lambda:prepare_chart_bars(market.get_bars('NQ1!','1m',start,end),'5m','24h',session_profile='futures_24h')[0])
record('chart_subset',lambda:prepare_chart_bars(market.get_bars('NQ1!','1m',pd.Timestamp('2026-06-11T00:00Z').to_pydatetime(),end),'5m','24h',session_profile='futures_24h')[0])
record('orb',lambda:service.run(dict(strategy_key='opening_range_breakout_research_v1',symbols=['NQ1!'],primary_timeframe='1m',session='24h',start_date='2026-06-09',end_date='2026-06-12',starting_balance=1e6,sizing_mode='quantity',risk_value=1,allow_overnight=False)))
scratch.cleanup()
