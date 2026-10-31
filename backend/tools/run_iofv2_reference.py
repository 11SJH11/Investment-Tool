#!/usr/bin/env python3
"""Independent OHLC research simulator for all 12 IOF V2 variants.

Single near-edge entry per zone; many different zones may coexist. This runner
is distinct from Ledger's single-position execution proxy. It contains no broker
functions and submits no real orders. All costs default to zero for research.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right, insort
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.backtesting.strategies.iof_v2_persistent_zones import DisplacementDetector, TF_MIN


@dataclass
class Position:
    zone: object
    entered_at: pd.Timestamp
    entry: float
    quantity: float
    initial_quantity: float
    stop: float
    risk_price: float
    initial_risk_cash: float
    remaining: float = 1.0
    tp1: bool = False
    tp2: bool = False
    net_pnl: float = 0.0
    exit_reasons: list | None = None

    def __post_init__(self):
        if self.exit_reasons is None:
            self.exit_reasons = []


def read_1m_csv(path):
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={k:v for k,v in {'time':'timestamp','datetime':'timestamp','date':'timestamp',
              'o':'open','h':'high','l':'low','c':'close'}.items() if k in df and v not in df})
    needed = {'timestamp','open','high','low','close'}
    if not needed.issubset(df.columns):
        raise ValueError('CSV needs: timestamp or time, open, high, low, close')
    if pd.api.types.is_numeric_dtype(df['timestamp']):
        unit='ms' if df['timestamp'].iloc[0] > 1e11 else 's'
        df['timestamp']=pd.to_datetime(df['timestamp'],utc=True,unit=unit)
    else:
        df['timestamp']=pd.to_datetime(df['timestamp'],utc=True)
    for c in ('open','high','low','close'):
        df[c]=pd.to_numeric(df[c],errors='raise')
    df=df.sort_values('timestamp').reset_index(drop=True)
    if df.empty or df['timestamp'].duplicated().any() or df['timestamp'].isna().any():
        raise ValueError('Timestamps must be nonempty and unique')
    if (df['high']<df[['open','close','low']].max(axis=1)).any() or (df['low']>df[['open','close','high']].min(axis=1)).any():
        raise ValueError('Invalid OHLC bars')
    return df


def candles_for_timeframe(df,tf,market='gold'):
    """Completed bars aligned to the market SESSION, not arbitrary UTC midnight.

    Gold: 17:00 America/New_York OANDA-style session anchor (DST-aware).
    QQQ: 09:30-16:00 America/New_York regular session (no extended bars).
    Incomplete last candles are not shown to the detector. DST-overlap buckets
    with too many minute bars are deliberately excluded as ambiguous.
    """
    if market not in ('gold','equity'):
        raise ValueError('market must be gold or equity')
    working=df[['timestamp','open','high','low','close']].copy()
    t=pd.to_datetime(working['timestamp'],utc=True).dt.tz_convert('America/New_York')
    minutes=t.dt.hour*60+t.dt.minute
    if market=='equity':
        in_session=(minutes>=570)&(minutes<960)
        excluded=int((~in_session).sum())
        working=working.loc[in_session].copy()
        local=t.loc[in_session]
        minutes=minutes.loc[in_session]
        anchor=570
        session_date=local.dt.date
    else:
        excluded=0
        anchor=1020
        session_date=(t-pd.Timedelta(hours=17)).dt.date
    if tf=='1m':
        return working.reset_index(drop=True),excluded
    n=TF_MIN[tf]
    working['_day']=session_date.to_numpy()
    working['_slot']=(((minutes-anchor)%1440)//n).to_numpy()
    grouped=working.sort_values('timestamp').groupby(['_day','_slot'],sort=True)
    counts=grouped['close'].count()
    # Different disjoint market sessions must never merge into one candle.
    aggregates=grouped.agg(timestamp=('timestamp','min'),open=('open','first'),
                           high=('high','max'),low=('low','min'),close=('close','last'))
    dropped=int((counts!=n).sum())+excluded
    complete=aggregates.loc[counts==n].reset_index(drop=True)
    return complete.sort_values('timestamp').reset_index(drop=True),dropped


def build_zones(frames,tf,variant,displacement_atr,efficiency,buffer):
    detector=DisplacementDetector(tf,variant=variant,displacement_atr=displacement_atr,
                                  min_efficiency=efficiency,stop_buffer_atr=buffer)
    zones=[]
    for bar in frames[tf].itertuples(index=False):
        z=detector.process(bar._asdict())
        if z is not None:
            zones.append(z)
    return zones


def run_variant(df,zones,*,starting_balance=10000.,risk_pct=1.,max_leverage=20.,max_open_positions=1):
    """1m bar simulation; one entry per zone; stop-first ambiguous ordering.

    Last 1m bar is known only at its close. Zones created by any timeframe
    become tradable on the FIRST NEXT one-minute candle.
    """
    if not zones:
        return ({'zones':0,'trades':0,'net_pnl':0.,'return_pct':0.,'total_r':0.,'win_rate_pct':None},[],[])
    zones=sorted(zones,key=lambda z:z.confirmed_at)
    active={}     # persistent untouched zones; NEVER expire by age
    prices=[]     # (entry, zone_id) sorted; filled entries remain inert
    positions=[]
    trades=[]
    events=[]
    balance=float(starting_balance)
    j=0
    for bar in df.itertuples(index=False):
        t=bar.timestamp
        high,low,op,close=float(bar.high),float(bar.low),float(bar.open),float(bar.close)
        # 1) Protective management for existing positions (from earlier candles)
        finished=[]
        for p in positions:
            d=1 if p.zone.direction=='long' else -1
            targets=[p.entry+d*p.risk_price*r for r in (1,2,3)]
            def booked(fraction,price,why):
                nonlocal balance
                if fraction<=1e-12: return
                qty=p.initial_quantity*fraction
                pnl=d*(price-p.entry)*qty
                balance+=pnl;p.net_pnl+=pnl;p.remaining-=fraction
                p.exit_reasons.append(why)
                events.append({'zone_id':p.zone.zone_id,'time':str(t),'reason':why,'price':price,
                               'fraction_original':fraction,'pnl':pnl})
            stop_hit = low<=p.stop if d==1 else high>=p.stop
            if stop_hit:
                # Stop first even if this bar also reached TP1/2/3.
                gap_price=min(op,p.stop) if d==1 else max(op,p.stop)
                booked(p.remaining,gap_price,'STOP' if not p.tp2 else 'BREAKEVEN')
                if p.zone.status!='tp2':p.zone.status='stopped'
            else:
                hit1=high>=targets[0] if d==1 else low<=targets[0]
                hit2=high>=targets[1] if d==1 else low<=targets[1]
                hit3=high>=targets[2] if d==1 else low<=targets[2]
                if not p.tp1 and hit1:
                    booked(.30,targets[0],'TP1');p.tp1=True
                if not p.tp2 and hit2:
                    booked(.30,targets[1],'TP2');p.tp2=True;p.zone.status='tp2';p.stop=p.entry
                if p.tp2 and p.remaining>1e-10:
                    # If BE and TP3 are both touched after TP2 on the same bar,
                    # assume adverse post-TP2 sequencing and grant BE, not TP3.
                    be_cross=low<=p.entry if d==1 else high>=p.entry
                    if be_cross:
                        booked(p.remaining,p.entry,'BE_SAME_BAR')
                    elif hit3:
                        booked(p.remaining,targets[2],'TP3')
            if p.remaining<1e-8:
                finished.append(p)
        for p in finished:
            trades.append({'zone_id':p.zone.zone_id,'timeframe':p.zone.timeframe,'direction':p.zone.direction,
                           'entry_time':str(p.entered_at),'exit_time':str(t),'entry':p.entry,
                           'initial_stop':p.zone.stop,'planned_risk_cash':p.initial_risk_cash,
                           'net_pnl':p.net_pnl,'net_r':p.net_pnl/p.initial_risk_cash if p.initial_risk_cash else 0.,
                           'exit_reasons':';'.join(p.exit_reasons),'zone_age_min':(p.entered_at-p.zone.confirmed_at).total_seconds()/60,
                           'zone_candles':p.zone.candles,'bos':p.zone.bos,'fvg':p.zone.fvg})
            positions.remove(p)
        # 2) Limit fills on this 1m bar for zones created BEFORE its open.
        prev_close=last_close if 'last_close' in locals() else op
        lo=min(low,prev_close,op)
        hi=max(high,prev_close,op)
        left=bisect_left(prices,(lo,'')); right=bisect_right(prices,(hi,'\uffff'))
        # Do not invent priority: price-nearest at previous bar close, older first.
        candidates=[]
        for _,zid in prices[left:right]:
            z=active.get(zid)
            if z is None or z.status!='active' or z.confirmed_at>t:
                continue
            if z.direction=='long':
                valid=prev_close>=z.entry and low<=z.entry
                raw_fill=min(op,z.entry)
                has_invalid_open=raw_fill<=z.stop
            else:
                valid=prev_close<=z.entry and high>=z.entry
                raw_fill=max(op,z.entry)
                has_invalid_open=raw_fill>=z.stop
            if valid:
                candidates.append((abs(prev_close-z.entry),z.confirmed_at,zid,raw_fill,has_invalid_open))
        candidates.sort()
        for _,_,zid,raw_fill,invalid in candidates:
            if len(positions)>=max_open_positions:
                break
            z=active[zid]
            if invalid:
                z.status='invalid_gap_past_stop';continue
            distance=abs(raw_fill-z.stop)
            if distance<=0:continue
            occupied_notional=sum(p.entry*p.quantity for p in positions)
            available=max(0.,balance*max_leverage-occupied_notional)
            quantity=min(balance*risk_pct/100./distance,available/raw_fill) if raw_fill>0 and balance>0 else 0.
            if quantity<=1e-10:continue
            risk_cash=quantity*distance
            p=Position(z,t,raw_fill,quantity,quantity,z.stop,distance,risk_cash)
            positions.append(p)
            z.status='filled'  # one entry per zone for baseline
            # Same-candle STOP FIRST, but favorable moves are only counted if
            # the close is beyond TP; the high could predate limit entry.
            d=1 if z.direction=='long' else -1
            crossed_stop=low<=p.stop if d==1 else high>=p.stop
            if crossed_stop:
                px=min(op,p.stop) if d==1 else max(op,p.stop)
                pnl=d*(px-p.entry)*quantity
                balance+=pnl;p.net_pnl=pnl;p.remaining=0.;z.status='stopped'
                p.exit_reasons.append('ENTRY_BAR_STOP')
                events.append({'zone_id':zid,'time':str(t),'reason':'ENTRY_BAR_STOP','price':px,'fraction_original':1.,'pnl':pnl})
                trades.append({'zone_id':zid,'timeframe':z.timeframe,'direction':z.direction,
                               'entry_time':str(t),'exit_time':str(t),'entry':p.entry,'initial_stop':z.stop,
                               'planned_risk_cash':risk_cash,'net_pnl':pnl,'net_r':pnl/risk_cash,
                               'exit_reasons':'ENTRY_BAR_STOP','zone_age_min':(t-z.confirmed_at).total_seconds()/60,
                               'zone_candles':z.candles,'bos':z.bos,'fvg':z.fvg})
                positions.remove(p)
            # else: do not grant instant TP on the entry candle based on its high.
            # Future candles handle targets. Conservatively defer any entry-bar
            # favorable close to the next bar's target evaluation.
        last_close=close
        # 3) Newly completed TF candle zones: available starting NEXT 1m candle.
        completed_at=t+pd.Timedelta(minutes=1)
        while j<len(zones) and zones[j].confirmed_at<=completed_at:
            z=zones[j];j+=1
            active[z.zone_id]=z
            insort(prices,(z.entry,z.zone_id))
    # mark to market at end of selected data, no phantom TP
    if len(df):
        last=df.iloc[-1]
        for p in positions:
            d=1 if p.zone.direction=='long' else -1
            pnl=d*(float(last['close'])-p.entry)*p.initial_quantity*p.remaining
            balance+=pnl;p.net_pnl+=pnl;p.exit_reasons.append('END_OF_DATA')
            trades.append({'zone_id':p.zone.zone_id,'timeframe':p.zone.timeframe,'direction':p.zone.direction,
                           'entry_time':str(p.entered_at),'exit_time':str(last['timestamp']),
                           'entry':p.entry,'initial_stop':p.zone.stop,'planned_risk_cash':p.initial_risk_cash,
                           'net_pnl':p.net_pnl,'net_r':p.net_pnl/p.initial_risk_cash,
                           'exit_reasons':';'.join(p.exit_reasons),'zone_age_min':(p.entered_at-p.zone.confirmed_at).total_seconds()/60,
                           'zone_candles':p.zone.candles,'bos':p.zone.bos,'fvg':p.zone.fvg})
    rs=pd.Series([x['net_r'] for x in trades],dtype=float)
    summary={'zones':len(zones),'trades':len(trades),'wins':int((rs>0).sum()),
             'win_rate_pct':round(float(100*(rs>0).mean()),2) if len(rs) else None,
             'total_r':round(float(rs.sum()),4),'average_r':round(float(rs.mean()),4) if len(rs) else None,
             'starting_balance':starting_balance,'ending_balance':round(balance,2),
             'net_pnl':round(balance-starting_balance,2),
             'return_pct':round(100*(balance/starting_balance-1),3),
             'unfilled_active_zones':sum(z.status=='active' for z in zones),
             'zero_cost_research':True,
             'execution_model':'multi-zone persistent; 1 entry/zone, 1m OHLC stop-first; no tick proof'}
    return summary,trades,events


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('csv',help='1m OHLC CSV with UTC timestamps')
    ap.add_argument('--out',default='iofv2_results')
    ap.add_argument('--market',choices=['gold','equity'],default='gold',help='Market-session anchoring for completed 1m/15m/1h/4h bars')
    ap.add_argument('--starting-balance',type=float,default=10000.)
    ap.add_argument('--risk-pct',type=float,default=1.)
    ap.add_argument('--max-leverage',type=float,default=20.)
    ap.add_argument('--max-open',type=int,default=1)
    ap.add_argument('--displacement-atr',type=float,default=2.)
    ap.add_argument('--min-efficiency',type=float,default=.65)
    ap.add_argument('--stop-buffer-atr',type=float,default=.1)
    ap.add_argument('--only-timeframe',choices=list(TF_MIN))
    ap.add_argument('--only-variant',choices=['basic','bos','bos_fvg'])
    args=ap.parse_args()
    if args.starting_balance<=0 or not 0<args.risk_pct<=100 or args.max_leverage<=0 or args.max_open<1:
        ap.error('Positive balance/leverage/positions and risk in (0,100] are required')
    df=read_1m_csv(args.csv)
    frames={}
    print(f'Loaded {len(df):,} 1-minute bars')
    for tf in ([args.only_timeframe] if args.only_timeframe else TF_MIN):
        frames[tf],incomplete=candles_for_timeframe(df,tf,args.market)
        print(f'{tf}: {len(frames[tf]):,} complete candles; {incomplete:,} incomplete buckets excluded')
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for tf in frames:
        for v in ([args.only_variant] if args.only_variant else ['basic','bos','bos_fvg']):
            zs=build_zones(frames,tf,v,args.displacement_atr,args.min_efficiency,args.stop_buffer_atr)
            stats,trades,events=run_variant(df,zs,starting_balance=args.starting_balance,
                      risk_pct=args.risk_pct,max_leverage=args.max_leverage,max_open_positions=args.max_open)
            stats.update(timeframe=tf,variant=v)
            print(tf,v,'zones',stats['zones'],'trades',stats['trades'],'totalR',stats['total_r'])
            rows.append(stats)
            stem=f'{tf}_{v}'
            pd.DataFrame(trades).to_csv(out/f'{stem}_trades.csv',index=False)
            pd.DataFrame(events).to_csv(out/f'{stem}_partials.csv',index=False)
            pd.DataFrame([vars(z) for z in zs]).to_csv(out/f'{stem}_zones.csv',index=False)
    pd.DataFrame(rows).to_csv(out/'comparison.csv',index=False)
    (out/'settings.json').write_text(json.dumps(vars(args),indent=2,default=str))
    print('Saved',out.resolve())

if __name__=='__main__':main()
