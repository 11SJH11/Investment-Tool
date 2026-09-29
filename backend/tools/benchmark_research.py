"""Offline benchmark. Generated OHLCV is a TEST FIXTURE, never market evidence."""
import argparse
import cProfile
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
parser.add_argument('--days',type=int,default=132)
parser.add_argument('--runs',type=int,default=2)
parser.add_argument('--profile',action='store_true')
parser.add_argument('--experiment',choices=['single','spectrum','grid'],default='single')
args=parser.parse_args()
scratch=tempfile.TemporaryDirectory(prefix='ledger-research-benchmark-', ignore_cleanup_errors=True)
os.environ['LEDGER_DATA_DIR']=scratch.name
sys.path.insert(0,args.app_root)
import pandas as pd
from app.services.backtest import BacktestService
from app.services.market_data import MarketDataService
try:
    from app.performance import Profile
except ImportError:  # Instrumented before snapshot.
    from app.services.performance import Profile
from app.storage.market_store import MarketStore
from app.storage.database import Database
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.backtest_run_repository import BacktestRunRepository

class FixtureProvider:
    key='fixture';cache_namespace='benchmark-fixture-v1';historical_delay_minutes=0
    historical_feed='synthetic-fixture';adjustment='unadjusted'
    def __init__(self):
        self.calls=0
        days=pd.bdate_range('2026-03-03',periods=args.days)
        frames=[]
        for day in days:
            ts=pd.date_range(str(day.date())+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
            f=pd.DataFrame(dict(timestamp=ts,open=100.,high=101.,low=99.,close=100.,volume=100.))
            f.loc[15,['open','high','low','close']]=[100,103,100,102]
            f.loc[16,['open','high','low','close']]=[103,105,102,104]
            f.loc[17,['open','high','low','close']]=[104,112,103,111]
            frames.append(f)
        self.minute=pd.concat(frames,ignore_index=True)
        daily_days=pd.bdate_range(days[0]-pd.Timedelta(days=220),days[-1])
        self.daily=pd.DataFrame(dict(timestamp=daily_days.tz_localize('UTC'),open=100.,high=112.,low=99.,close=100.,volume=39000.))
        self.start,self.end=days[0].date().isoformat(),days[-1].date().isoformat()
    def get_bars(self,symbol,timeframe,start,end):
        self.calls+=1
        f=self.daily if timeframe=='1d' else self.minute
        return f.loc[(f.timestamp>=start)&(f.timestamp<=end)].copy()

root=Path(scratch.name);db=Database(root/'fixture.sqlite');db.initialize()
provider=FixtureProvider();store=MarketStore(root/'market')
market=MarketDataService(provider,store,MarketCacheRepository(db))
service=BacktestService(market,BacktestRunRepository(db))
request=dict(strategy_key='opening_range_breakout_research_v1',symbols=['SPY'],primary_timeframe='1m',session='regular',start_date=provider.start,end_date=provider.end,starting_balance=1e6,sizing_mode='quantity',risk_value=1,allow_overnight=False)
output={'fixture':True,'experiment':args.experiment,'days':args.days,'bars':len(provider.minute),'period':[provider.start,provider.end],'runs':[]}
profiler=cProfile.Profile()
if args.experiment=='spectrum':
    configs=[{**request,'strategy_params':{'min_breakout_range_atr':v/4}} for v in range(10)]
elif args.experiment=='grid':
    configs=[{**request,'strategy_params':{'min_breakout_range_atr':x,'min_breakout_body_ratio':y}}
             for x in [-1,0,.5,1,1.5] for y in [-1,0,.25,.5,.75]]
else:
    configs=[request]*args.runs
for i, config in enumerate(configs):
    before=provider.calls
    if args.profile:profiler.enable()
    with Profile() as timings:
        start=perf_counter();result=service.run(config);elapsed=perf_counter()-start
    if args.profile:profiler.disable()
    digest=hashlib.sha256(json.dumps({k:result[k] for k in ('trades','metrics','setups')},sort_keys=True,default=str).encode()).hexdigest()
    row=dict(index=i,provider_calls=provider.calls-before,digest=digest,**timings.snapshot())
    # Keep total separate from stage durations.
    row['wall_seconds']=elapsed
    row['parameters']=config.get('strategy_params',{})
    try:
        from app.frame_cache import frames
        row['cache']=frames.stats()
    except ImportError:
        pass
    output['runs'].append(row)
    Path(args.output).write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(row),flush=True)
if args.profile:
    profiler.dump_stats(args.output+'.prof')
scratch.cleanup()
