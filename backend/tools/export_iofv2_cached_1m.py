#!/usr/bin/env python3
"""Export ONE identified, previously cached Ledger 1m source to OHLC CSV.

No provider requests, writes to Ledger data, migrations or credentials output.
When multiple provider caches exist, require --namespace explicitly.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.storage.market_store import MarketStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol',required=True,help='Ledger symbol, e.g. XAUUSD or QQQ')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--namespace',help='Cache namespace shown by --list')
    parser.add_argument('--list',action='store_true',help='Show available source files only')
    parser.add_argument('--start',help='UTC yyyy-mm-dd (inclusive)')
    parser.add_argument('--end',help='UTC yyyy-mm-dd (inclusive)')
    args=parser.parse_args()
    settings=get_settings()
    store=MarketStore(settings.market_data_dir)
    safe_symbol=args.symbol.upper().replace('/','-')
    root=store.root/'bars'
    candidates=sorted(root.glob(f'*/1m/{safe_symbol}.parquet'))
    if args.list:
        for p in candidates:
            print(f'namespace={p.parent.parent.name}  path={p}')
        if not candidates:
            print('No cached 1m bars for', args.symbol, 'in',root)
        return
    if args.out is None and not args.list:
        parser.error('--out is required unless --list is set')
    if args.namespace:
        candidates=[p for p in candidates if p.parent.parent.name==args.namespace.replace('/','-')]
    if len(candidates)!=1:
        print(f'Found {len(candidates)} matching 1m cache(s). Specify --namespace if several exist:')
        for p in candidates:
            print(' ',p.parent.parent.name,':',p)
        raise SystemExit(2)
    path=candidates[0]
    # Read directly; no provider fetch or mutation of a data cache.
    import duckdb
    con=duckdb.connect()
    try:
        clauses=[]; params=[str(path)]
        if args.start:
            clauses.append('timestamp >= ?');params.append(args.start+'T00:00:00+00:00')
        if args.end:
            finish=pd.Timestamp(args.end,tz='UTC')+pd.Timedelta(days=1)
            clauses.append('timestamp < ?');params.append(finish.isoformat())
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        df=con.execute('SELECT timestamp,open,high,low,close FROM read_parquet(?)'+where+' ORDER BY timestamp',params).df()
    finally:
        con.close()
    if df.empty:
        raise SystemExit('No 1m bars in chosen cache/time range')
    df['timestamp']=pd.to_datetime(df['timestamp'],utc=True)
    if df['timestamp'].duplicated().any():
        raise SystemExit('Duplicate timestamps: export rejected')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(args.out,index=False)
    manifest={
        'symbol':args.symbol, 'cache_namespace':path.parent.parent.name,
        'cache_source':str(path.resolve()), 'rows':len(df),
        'first_utc':df['timestamp'].iloc[0].isoformat(),
        'last_utc':df['timestamp'].iloc[-1].isoformat(),
        'note':'Existing cached bars only; no refresh or data-provider call. Validate corporate-action adjustments and market data gaps separately.'
    }
    args.out.with_suffix('.source.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Wrote',len(df),'bars:',args.out.resolve())
    print('Source namespace:',path.parent.parent.name)


if __name__=='__main__':main()
