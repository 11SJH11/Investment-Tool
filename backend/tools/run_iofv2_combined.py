#!/usr/bin/env python3
"""IOF V2 15m + 4h SHARED-ACCOUNT single/ladder portfolio research.

Runs the already installed IOF V2 detector + ladder engine. This is a new
research runner, NOT a trading bridge. It does not modify Ledger's engine,
strategies, database or brokers, and performs no network access.

Unlike summing two separate backtest summaries, combined simulations share a
single chronological sequence of 1m bars, balance, notional cap, campaigns,
and number of open slots. Never include all three 4h confirmation variants
simultaneously: their zones are highly overlapping hypotheses.
"""
from __future__ import annotations

import argparse
import json
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.run_iofv2_ladder import run_ladder
from tools.run_iofv2_reference import read_1m_csv, candles_for_timeframe, build_zones

VARIANTS = ('basic', 'bos', 'bos_fvg')
CONFIGS = ('15m_only', '4h_only', 'combined_1slot', 'combined_2slots')


def selected_zones(zones_15m, zones_4h, config):
    """Keep only preselected, independent timeframes; never invent new zones."""
    if config not in CONFIGS:
        raise ValueError('Unrecognised portfolio')
    zones = (list(zones_15m) if config != '4h_only' else []) + (
        list(zones_4h) if config != '15m_only' else [])
    ids = [z.zone_id for z in zones]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate zone IDs across selected detectors; cannot simulate safely')
    return sorted(zones, key=lambda z: (z.confirmed_at, z.timeframe, z.zone_id))


def config_risk(config, risk_pct, two_slot_risk_pct):
    """A maximum of 1% planned active risk if risk_pct=1 and two_slot=.5."""
    if config not in CONFIGS:
        raise ValueError('Unknown portfolio')
    if config == 'combined_2slots':
        return 2, two_slot_risk_pct
    return 1, risk_pct


def portfolio_stats(stats, campaigns, timeframe_counts):
    """Separate the two sources without pretending their standalone returns add."""
    result = dict(stats)
    result.setdefault('max_1m_close_equity_drawdown_pct', 0.)
    result.setdefault('multi_rung_campaigns', 0)
    result.setdefault('win_rate_pct', None)
    result.setdefault('average_r_per_campaign', None)
    for tf in ('15m','4h'):
        rows = [c for c in campaigns if c['timeframe'] == tf]
        result[f'{tf}_detected_zones'] = timeframe_counts.get(tf, 0)
        result[f'{tf}_completed_campaigns'] = len(rows)
        result[f'{tf}_campaign_net_pnl'] = round(sum(c['net_pnl'] for c in rows), 2)
        result[f'{tf}_campaign_total_r'] = round(sum(c['campaign_r'] for c in rows), 4)
        result[f'{tf}_multi_rung_campaigns'] = sum(c['rungs_filled']>1 for c in rows)
    return result


def run_configs(df, zones_15m, zones_4h, *, configurations=CONFIGS,
                entry_modes=('single','ladder'), step_price=0.10, max_rungs=8,
                allocation='front_loaded', starting_balance=10000.,
                risk_pct=1., two_slot_risk_pct=.5, max_leverage=20.,
                spread_price=0., slippage_price=0.):
    """Yield each actual, independent portfolio simulation with its fills."""
    if not (0 < two_slot_risk_pct <= risk_pct / 2. + 1e-12):
        raise ValueError('Two-slot per-zone risk must be <= half the baseline risk')
    for config in configurations:
        selected = selected_zones(zones_15m,zones_4h,config)
        slots,zone_risk = config_risk(config,risk_pct,two_slot_risk_pct)
        for mode in entry_modes:
            stats,campaigns,events,states = run_ladder(
                df, selected, starting_balance=starting_balance, risk_pct=zone_risk,
                max_leverage=max_leverage, max_open=slots, step_price=step_price,
                max_rungs=max_rungs, allocation=allocation, entry_mode=mode,
                spread_price=spread_price, slippage_price=slippage_price,
            )
            stats = portfolio_stats(stats,campaigns,{
                '15m':len(zones_15m) if config!='4h_only' else 0,
                '4h':len(zones_4h) if config!='15m_only' else 0,
            })
            stats.update(portfolio=config,entry_mode=mode,open_slots=slots,
                         risk_pct_per_campaign=zone_risk,
                         nominal_max_active_risk_pct=slots*zone_risk,
                         step_price=step_price,allocation=allocation,max_rungs=max_rungs)
            zone_tf = {z.zone_id: z.timeframe for z in selected}
            for event in events:
                event['timeframe'] = zone_tf.get(event['zone_id'])
            for state in states:
                state['timeframe'] = zone_tf.get(state['zone_id'])
            yield config,mode,stats,campaigns,events,states


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('csv',help='Previously exported 1m OHLC data, e.g. ~/iofv2_gold_1m.csv')
    p.add_argument('--out',default='iofv2_gold_combined',help='New output directory; do not reuse original results')
    p.add_argument('--market',choices=('gold','equity'),default='gold')
    p.add_argument('--15m-variant',dest='m15_variant',choices=VARIANTS,default='basic')
    p.add_argument('--4h-variant',dest='h4_variant',choices=VARIANTS,default='basic')
    p.add_argument('--portfolio',choices=('all',)+CONFIGS,default='all')
    p.add_argument('--entry-mode',choices=('both','single','ladder'),default='both')
    p.add_argument('--step-price',type=float,required=True,help='Absolute price units; Gold pip mapping must be checked')
    p.add_argument('--max-rungs',type=int,default=8)
    p.add_argument('--allocation',choices=('equal','front_loaded'),default='front_loaded')
    p.add_argument('--starting-balance',type=float,default=10000.)
    p.add_argument('--risk-pct',type=float,default=1.,help='Per campaign for solo and combined 1-slot portfolios')
    p.add_argument('--two-slot-risk-pct',type=float,default=.5,help='Per campaign for combined 2-slot portfolio')
    p.add_argument('--max-leverage',type=float,default=20.)
    p.add_argument('--displacement-atr',type=float,default=2.)
    p.add_argument('--min-efficiency',type=float,default=.65)
    p.add_argument('--stop-buffer-atr',type=float,default=.10)
    p.add_argument('--spread-price',type=float,default=0.,
                   help='FULL round-trip spread in absolute instrument price units')
    p.add_argument('--slippage-price',type=float,default=0.,
                   help='Additional adverse slippage per execution SIDE, in price units')
    p.add_argument('--start',help='UTC inclusive start YYYY-MM-DD; requires warmup bars before start')
    p.add_argument('--end',help='UTC exclusive end YYYY-MM-DD')
    p.add_argument('--test-role',choices=('development','validation'),default='development')
    p.add_argument('--freeze-from',type=Path,
                   help='2025 corrected development settings.json: verify strategy code and signal params')
    args=p.parse_args()
    if not (args.step_price>0 and args.max_rungs>=1 and args.starting_balance>0 and
            args.max_leverage>0 and 0<args.risk_pct<=100 and
            0<args.two_slot_risk_pct<=args.risk_pct/2. and
            0<=args.spread_price and 0<=args.slippage_price):
        p.error('Invalid price/risk settings. Two-slot risk per zone must be <= half the one-slot risk.')
    out=Path(args.out).expanduser()
    if out.exists() and any(out.iterdir()):
        p.error(f'Output folder is not empty: {out}. Use a new folder to avoid overwriting tests.')
    root=Path(__file__).resolve().parents[1]
    implementations={
        rel:hashlib.sha256((root/rel).read_bytes()).hexdigest()
        for rel in ('app/backtesting/strategies/iof_v2_persistent_zones.py',
                    'tools/run_iofv2_reference.py', 'tools/run_iofv2_ladder.py',
                    'tools/run_iofv2_combined.py')}
    freeze_keys=('m15_variant','h4_variant','step_price','max_rungs','allocation',
                 'max_leverage','displacement_atr','min_efficiency','stop_buffer_atr')
    if args.freeze_from:
        frozen=json.loads(args.freeze_from.expanduser().read_text())
        for key in freeze_keys:
            if frozen.get(key)!=getattr(args,key):
                p.error(f'Frozen signal parameter mismatch: {key} ' +
                        f'{getattr(args,key)!r} != {frozen.get(key)!r}')
        if frozen.get('implementations') != implementations:
            p.error('Strategy/simulator source changed since frozen development run')
    if args.test_role=='validation' and (not args.start or args.start<'2026-01-01'):
        p.error('Validation requires --start >= 2026-01-01 and a frozen development manifest')
    if args.test_role=='validation' and not args.freeze_from:
        p.error('Validation requires --freeze-from with a development manifest')
    df_all=read_1m_csv(Path(args.csv).expanduser())
    start=pd.Timestamp(args.start,tz='UTC') if args.start else None
    end=pd.Timestamp(args.end,tz='UTC') if args.end else None
    if start is not None and end is not None and end<=start:
        p.error('--end must be later than --start')
    # Exclude all future candles *before* detecting zones, never just before trading.
    df_for_detection=df_all.loc[df_all.timestamp<end].copy() if end is not None else df_all
    if len(df_for_detection)<240:
        p.error('Insufficient 1m candles for the 4h detector')
    df=df_for_detection.loc[df_for_detection.timestamp>=start].copy() if start is not None else df_for_detection
    if df.empty:
        p.error('No data in execution period; export the requested cached 1m range')
    if start is not None and (df_for_detection.timestamp<start).sum()<1000:
        p.error('Need >= 1000 preceding 1m warmup bars in CSV before --start')
    print(f'Loaded {len(df):,} execution 1m bars ({df.timestamp.iloc[0]} through {df.timestamp.iloc[-1]})',flush=True)
    frames={}
    for tf in ('15m','4h'):
        frames[tf],incomplete=candles_for_timeframe(df_for_detection,tf,args.market)
        print(f'{tf}: {len(frames[tf]):,} completed candles ({incomplete:,} excluded buckets)',flush=True)
    zones15=build_zones(frames,'15m',args.m15_variant,args.displacement_atr,args.min_efficiency,args.stop_buffer_atr)
    zones4=build_zones(frames,'4h',args.h4_variant,args.displacement_atr,args.min_efficiency,args.stop_buffer_atr)
    # Restrict validation to zones confirmed in the unseen execution period.
    # Pre-start warmup is for causal ATR/detector state, not trading 2025 zones.
    if start is not None:
        zones15=[z for z in zones15 if z.confirmed_at>=start]
        zones4=[z for z in zones4 if z.confirmed_at>=start]
    print(f'Detected {len(zones15):,} 15m {args.m15_variant} zones and {len(zones4):,} 4h {args.h4_variant} zones',flush=True)
    configs = CONFIGS if args.portfolio=='all' else (args.portfolio,)
    modes = ('single','ladder') if args.entry_mode=='both' else (args.entry_mode,)
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for config,mode,stats,campaigns,events,states in run_configs(
        df,zones15,zones4, configurations=configs,entry_modes=modes,
        step_price=args.step_price,max_rungs=args.max_rungs,allocation=args.allocation,
        starting_balance=args.starting_balance,risk_pct=args.risk_pct,
        two_slot_risk_pct=args.two_slot_risk_pct,max_leverage=args.max_leverage,
        spread_price=args.spread_price,slippage_price=args.slippage_price,
    ):
        rows.append(stats)
        stem=f'{config}_{mode}'
        pd.DataFrame(campaigns).to_csv(out/f'{stem}_campaigns.csv',index=False)
        pd.DataFrame(events).to_csv(out/f'{stem}_fills_and_exits.csv',index=False)
        pd.DataFrame(states).to_csv(out/f'{stem}_zone_states.csv',index=False)
        print(f'{stem}: return={stats["return_pct"]:+.3f}% DD={stats["max_1m_close_equity_drawdown_pct"]:.3f}% '
              f'campaigns={stats["campaigns"]:,} 15m={stats["15m_completed_campaigns"]} 4h={stats["4h_completed_campaigns"]}',flush=True)
    pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False)
    manifest=dict(vars(args))
    manifest.update(version='iofv2_efficiency_v21',simulator='run_iofv2_ladder.run_ladder',
                    implementations=implementations,
                    input_sha256=hashlib.sha256(Path(args.csv).expanduser().read_bytes()).hexdigest(),
                    trade_start=str(df.timestamp.iloc[0]), trade_end=str(df.timestamp.iloc[-1]),
                    warmup_start=str(df_for_detection.timestamp.iloc[0]),
                    tested_first_bar=str(df.timestamp.iloc[0]),tested_last_bar=str(df.timestamp.iloc[-1]),
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    note='Costs modelled as half quoted spread and additional adverse slippage PER SIDE; '
                         'zero when flags are zero. 1m OHLC conservative stop-first, not tick proof. '
                         'For --start, only zones confirmed on/after start are traded (prior bars = indicator warmup). '
                         'Do not sum standalone returns. No broker calls.')
    (out/'settings.json').write_text(json.dumps(manifest,indent=2,default=str),encoding='utf-8')
    pd.DataFrame([vars(z) for z in zones15+zones4]).to_csv(out/'detected_zones.csv',index=False)
    print('Saved',out.resolve(),flush=True)

if __name__=='__main__':
    main()
