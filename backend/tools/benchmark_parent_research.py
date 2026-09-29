"""Exact identical 5x5 fixture benchmark: old thread queue vs parent CPU workers.

All data/SQLite are isolated. Fixture timings are not live market/provider claims.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from threading import Lock
from time import perf_counter, process_time, sleep


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app-root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=['many','parent'],default='parent')
    parser.add_argument('--workers',default='1')
    parser.add_argument('--days',type=int,default=5)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='ledger-parent-benchmark-',ignore_cleanup_errors=True) as scratch:
        os.environ['LEDGER_DATA_DIR']=scratch
        sys.path.insert(0,args.app_root)
        import pandas as pd
        from app.services.backtest import BacktestService
        from app.services.backtest_jobs import BacktestJobs
        from app.services.market_data import MarketDataService
        from app.services.research_experiments import children
        from app.storage.database import Database
        from app.storage.market_store import MarketStore
        from app.storage.market_cache_repository import MarketCacheRepository
        from app.storage.backtest_run_repository import BacktestRunRepository
        from app.performance import Profile
        class Provider:
            key='fixture';cache_namespace='research-benchmark-v1'
            def __init__(self):
                self.calls=0;frames=[]
                days=pd.bdate_range('2026-03-03',periods=args.days)
                for day in days:
                    ts=pd.date_range(str(day.date())+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
                    f=pd.DataFrame(dict(timestamp=ts,open=100.,high=101.,low=99.,close=100.,volume=100.))
                    f.loc[15,['open','high','low','close']]=[100,103,100,102]
                    f.loc[16,['open','high','low','close']]=[103,105,102,104]
                    f.loc[17,['open','high','low','close']]=[104,112,103,111]
                    frames.append(f)
                self.frame=pd.concat(frames,ignore_index=True)
                ds=pd.bdate_range(days[0]-pd.Timedelta(days=220),days[-1]).tz_localize('UTC')
                self.daily=pd.DataFrame(dict(timestamp=ds,open=100.,high=112.,low=99.,close=100.,volume=39000.))
                self.start,self.end=days[0].date().isoformat(),days[-1].date().isoformat()
            def get_bars(self,symbol,tf,start,end):
                self.calls+=1;f=self.daily if tf=='1d' else self.frame
                return f.loc[(f.timestamp>=start)&(f.timestamp<=end)].copy()
        p=Provider();db=Database(Path(scratch)/'fixture.sqlite');db.initialize()
        market=MarketDataService(p,MarketStore(Path(scratch)/'market'),MarketCacheRepository(db))
        service=BacktestService(market,BacktestRunRepository(db))
        base=dict(strategy_key='opening_range_breakout_research_v1',symbols=['SPY'],primary_timeframe='1m',session='regular',
                  start_date=p.start,end_date=p.end,starting_balance=1e6,sizing_mode='quantity',risk_value=1,allow_overnight=False)
        axes=[dict(parameter='min_breakout_range_atr',values=[-1,0,.5,1,1.5]),dict(parameter='min_breakout_body_ratio',values=[-1,0,.25,.5,.75])]
        plan,runs=children(base,axes,'benchmark','5x5 exact fixture')
        # Warm the same primary, daily and diagnostic ranges without a simulation.
        start=pd.Timestamp(p.start,tz='America/New_York').to_pydatetime()
        end=(pd.Timestamp(p.end,tz='America/New_York')+pd.Timedelta(days=1)).to_pydatetime()
        for tf,a,b in [('1m',start,end),('1d',start-pd.Timedelta(days=200),end),('1m',start-pd.Timedelta(days=60),start)]:
            service._load_timeframe('SPY',tf,a,b,'regular')
        calls=p.calls;timings=[];lock=Lock();original=service.run
        def tracked(*a,**kw):
            with Profile() as profile:result=original(*a,**kw)
            with lock:timings.append(profile.snapshot())
            return result
        service.run=tracked
        queue=BacktestJobs(db,service,workers=2)
        t=perf_counter();cpu=process_time()
        try:
            if args.mode=='many':jobs=queue.enqueue(runs,'grid')
            else:
                parent={**base,'experiment_group':'research:benchmark','experiment_type':'interaction',
                        'run_name':'5x5 exact fixture','test_role':'development','research_workers':args.workers,
                        'research_base':base,'research_plan':plan,'research_children':runs}
                jobs=queue.enqueue([parent],'grid')
            while True:
                current=[queue.get(j['id']) for j in jobs]
                if all(j['status'] in ('completed','failed','cancelled') for j in current):break
                sleep(.2)
            elapsed=perf_counter()-t;cpu=process_time()-cpu
            saved=service.runs.list_by_experiment('research:benchmark')
            cells=[]
            for r in saved:
                selected={k:r['result'][k] for k in ('trades','metrics','setups','analysis','equity_curve')}
                cells.append({'index':r['config']['research_experiment']['cell_index'],
                              'digest':hashlib.sha256(json.dumps(selected,sort_keys=True,default=str).encode()).hexdigest()})
            output={'fixture':True,'days':args.days,'bars':len(p.frame),'mode':args.mode,'requested_workers':args.workers,
                    'logical_cpus':os.cpu_count(),'wall_seconds':elapsed,'parent_cpu_seconds':cpu,
                    'provider_calls':p.calls-calls,'queue_rows':len(jobs),'statuses':[j['status'] for j in current],
                    'cells':sorted(cells,key=lambda c:c['index']),'timings':timings}
            if args.mode=='parent':output['experiment']=queue.research.get('research:benchmark')
            try:
                from app.research_runtime import memory_info
                output['memory']=memory_info()
            except ImportError:pass
            Path(args.output).write_text(json.dumps(output,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in output.items() if k not in ('cells','timings','experiment')}),flush=True)
            assert len(cells)==25 and all(j['status']=='completed' for j in current), 'Benchmark failed'
        finally:queue.close()


if __name__=='__main__':main()
