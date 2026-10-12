"""Opt-in cache-only profiler. Never loads settings, providers or the user's DB.

Outputs are written only to --output. Run one case at a time for serial timings.
Example: python -B tools/audit_backtest_performance.py --strategy KEY --start
2026-01-01 --end 2026-03-31 --output C:/temp/ledger-profile --seconds 180
"""
import argparse
from collections import defaultdict
import cProfile
from functools import wraps
import json
from pathlib import Path
import pstats
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def io_counters():
    """Windows process I/O, not a claim about physical disk throughput."""
    import ctypes
    import os
    if os.name!='nt':return {}
    class Counters(ctypes.Structure):
        _fields_=[(n,ctypes.c_ulonglong) for n in ('read_operations','write_operations','other_operations','read_bytes','write_bytes','other_bytes')]
    kernel=ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    counts=Counters()
    if not kernel.GetProcessIoCounters(ctypes.c_void_p(kernel.GetCurrentProcess()),ctypes.byref(counts)):return {}
    return {name:getattr(counts,name) for name,_ in counts._fields_}


def run(args):
    from app.performance import Profile
    from app.research_runtime import memory_info
    from app.storage.market_store import MarketStore
    from app.services.backtest import BacktestService
    from app.backtesting.strategies import strategy_registry
    from app.backtesting.context import StrategyContext
    from app.data.instruments import instrument_spec
    from app.storage.database import Database
    from app.storage.backtest_run_repository import BacktestRunRepository
    import app.backtesting.engine as engine
    import app.services.backtest as backtest_module
    import importlib
    common_name='app.backtesting.strategies.vwap_confluence_common'
    try:common=importlib.import_module(common_name)
    except ModuleNotFoundError as exc:
        if exc.name!=common_name:raise
        common=None  # Local research children are not required for the parent audit.
    if args.reference_normalizer:
        from tests.fixtures.vwap_session_reference import normalise_1m
        import app.backtesting.strategies.vwap_trend_entry_exit_distance_research_v4 as v4
        v4._normalise_1m=normalise_1m
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    spans=defaultdict(lambda:{'wall_seconds':0.,'cpu_seconds':0.,'calls':0})
    patches=[]
    def instrument(owner,name,label):
        original=getattr(owner,name)
        @wraps(original)
        def wrapped(*a,**kw):
            wall=perf_counter();cpu=process_time()
            try:return original(*a,**kw)
            finally:
                row=spans[label];row['wall_seconds']+=perf_counter()-wall;row['cpu_seconds']+=process_time()-cpu;row['calls']+=1
        setattr(owner,name,wrapped);patches.append((owner,name,original))
    class CacheOnly:
        provider=SimpleNamespace(key='alpaca',cache_namespace=args.namespace,historical_delay_minutes=0)
        def __init__(self):self.store=MarketStore(Path(args.cache))
        def instrument_info(self,symbol):return instrument_spec(symbol)
        def provider_for(self,symbol):return self.provider
        def get_bars(self,symbol,timeframe,start,end):
            frame=self.store.read_bars(args.namespace,symbol,timeframe,start,end)
            if frame.empty:raise ValueError('Requested cache is empty; network fallback forbidden')
            return frame.loc[frame.timestamp<end].reset_index(drop=True)
    instrument(CacheOnly,'get_bars','data_load')
    instrument(backtest_module,'prepare_chart_bars','aggregation_and_session_filter')
    instrument(StrategyContext,'bars','context_bars')
    instrument(engine,'_row_to_series','row_to_series')
    instrument(engine.BacktestEngine,'run','engine_inclusive')
    for name in ['_merge_equity_points','_decorate_equity_curve','calculate_metrics','calculate_analysis']:
        if hasattr(engine,name):instrument(engine,name,name)
    for name in ['strict_pivots','break_events','_fvg_events','_rth','causal_swing_s5_samebar_within5']:
        if common is not None:instrument(common,name,'feature_'+name)
    cls=strategy_registry._items[args.strategy]
    instrument(cls,'on_bar','strategy_on_bar_inclusive')
    instrument(BacktestRunRepository,'create','database_save_inclusive')
    db=Database(output/'isolated.db');db.initialize()
    service=BacktestService(CacheOnly(),BacktestRunRepository(db))
    payload=dict(strategy_key=args.strategy,symbols=['QQQ'],primary_timeframe='1m',session='regular',
        start_date=args.start,end_date=args.end,starting_balance=10000,sizing_mode='position_pct',risk_value=100,
        max_leverage=1,commission_per_order=0,spread_bps=0,slippage_bps=0,allow_overnight=False,force_close_time='16:00',
        strategy_params={'min_confirmation_displacement_bps':6.0} if args.strategy=='vwap_trend_confirmation_quality_research_v5' else {},save_run=True)
    if args.entry_start:
        payload['entry_windows']=[dict(start=args.entry_start,end=args.entry_end)]
    progress_state={};started=perf_counter();cpu=process_time();profiler=cProfile.Profile()
    def progress(phase,done,total):
        progress_state.update(phase=phase,processed=done,total=total)
        if perf_counter()-started>args.seconds:raise TimeoutError('Benchmark wall budget reached')
    result=None;failure=None
    before_memory=memory_info();before_io=io_counters()
    with Profile() as profile:
        if not args.no_profile:profiler.enable()
        try:result=service.run(payload,progress=progress)
        except TimeoutError:failure='BOUNDED_BENCHMARK_TIMEOUT'
        finally:profiler.disable()
        wall=perf_counter()-started;cpu_elapsed=process_time()-cpu
        report=dict(strategy=args.strategy,start=args.start,end=args.end,status='COMPLETED' if result else failure,
            wall_seconds=wall,cpu_seconds=cpu_elapsed,cpu_core_equivalents=cpu_elapsed/wall,
            worker_count=1,progress=progress_state,profile=profile.snapshot(),inclusive_spans=dict(spans),
            memory_before=before_memory,memory_after=memory_info(),source=strategy_registry.provenance(args.strategy),
            process_io_delta={k:v-before_io[k] for k,v in io_counters().items()},
            config=payload,reference_normalizer=args.reference_normalizer,cprofile=not args.no_profile,
            scope='Cache-only serial case on a busy workstation; timing wrappers and optional cProfile add overhead. Span totals overlap. Entry windows are explicit in config; absent means all-day eligibility.')
        if result:
            report['bars']=result['data']['bar_counts'];report['metrics']=result['metrics']
            report['data_fingerprint']=result['data']['fingerprint']
            (output/'result.json').write_text(json.dumps(result,default=str),encoding='utf-8')
            # Engine callbacks are emitted every 64 timestamps; the final callback
            # can lag the successfully completed result. Do not undercount throughput.
            total=report['bars']['QQQ']['1m']
            progress_state.update(phase='completed',processed=total,total=total)
        processed=progress_state.get('processed') or 0
        report['observed_bars_per_second']=processed/wall
        if not args.no_profile:
            stats=pstats.Stats(profiler)
            report['hot_functions']=[dict(file=k[0],line=k[1],function=k[2],calls=v[1],self_seconds=v[2],inclusive_seconds=v[3])
                for k,v in sorted(stats.stats.items(),key=lambda pair:pair[1][2],reverse=True)[:60]]
            profiler.dump_stats(str(output/'profile.prof'))
        (output/'report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in {'hot_functions','config','source'}},indent=2))
    for owner,name,original in reversed(patches):setattr(owner,name,original)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy',required=True);parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--seconds',type=int,default=180)
    parser.add_argument('--cache',default=str(Path(__file__).resolve().parents[1]/'data/market'))
    parser.add_argument('--namespace',default='alpaca-sip-split')
    parser.add_argument('--reference-normalizer',action='store_true',help='Use the frozen pre-audit session normalizer for exact before/after comparison')
    parser.add_argument('--no-profile',action='store_true',help='Disable cProfile for representative wall-time measurements')
    parser.add_argument('--entry-start',help='Optional exchange-local entry window, e.g. 09:30')
    parser.add_argument('--entry-end',help='Optional exchange-local entry window, e.g. 11:30')
    args=parser.parse_args()
    if bool(args.entry_start)!=bool(args.entry_end):parser.error('Provide both entry-window boundaries')
    run(args)
