"""Replay registered V2A on provisional MT5 snapshots. No broker code or order submission.

Requires frozen V2A and parent strategy modules installed in local Ledger backend.
Timestamp semantics are UNVERIFIED, therefore results are diagnostic shadow signals ONLY.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

STRATEGY_KEY='mtf_v2a_h1_m5_long_only'
FORMAT='ledger-v2a-provisional-mt5-snapshot-v1'
EXPECTED_SOURCES={
 'app/backtesting/strategies/experimental_strategy_batch_2026_v1.py': '87f138abece8b9271b98c3da01c94a9f9ff81df3c3f7773991c386bd86275fc4',
 'app/backtesting/strategies/mtf_ict_research_v2.py': '64e5cc96db3970153b1529c4fb43e8a539cda7695b17aafe17cc14662fb2a0ad',
}
STRATEGY_FILES=tuple(EXPECTED_SOURCES)
FIVE_MINUTES=300


def validate_snapshot(snapshot):
    if (not isinstance(snapshot,dict) or snapshot.get('format')!=FORMAT or
        snapshot.get('timestamp_contract')!='UNVERIFIED_RAW_BROKER_EPOCH' or
        snapshot.get('environment')!='demo' or snapshot.get('symbol')!='XAUUSDs' or
        snapshot.get('strategy_key')!=STRATEGY_KEY or
        not isinstance(snapshot.get('account_key'),str) or len(snapshot['account_key'])!=64):
        raise ValueError('Unexpected snapshot identity / unverified format')
    if snapshot.get('orders_sent') is not False or snapshot.get('execution_enabled') is not False:
        raise ValueError('Execution-capable snapshots are not accepted')
    timestamp=int(snapshot['captured_at_epoch'])
    if not 0 <= int(time.time())-timestamp <= 120:
        raise ValueError('Snapshot is stale or from the future')
    frames=snapshot.get('bars')
    if not isinstance(frames,dict) or set(frames)!={'5m','1h','1d'}:
        raise ValueError('Missing bar timeframes')
    for tf, minimum in [('5m',300),('1h',18),('1d',26)]:
        rows=frames[tf]
        if not isinstance(rows,list) or len(rows)<minimum:
            raise ValueError('Insufficient '+tf+' history')
        prev=None
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'time','open','high','low','close','volume'}:
                raise ValueError('Malformed '+tf+' history')
            from math import isfinite
            stamp=row['time']
            if type(stamp) is not int or (prev is not None and stamp<=prev):
                raise ValueError('Duplicate/out-of-order '+tf+' bar')
            o,h,l,c,v=(float(row[k]) for k in ('open','high','low','close','volume'))
            if not all(map(isfinite,(o,h,l,c,v))) or l<=0 or v<0 or h<max(o,c,l) or l>min(o,c):
                raise ValueError('Invalid '+tf+' OHLC')
            prev=stamp
    if snapshot['open_positions']<0 or snapshot['pending_orders']<0:
        raise ValueError('Invalid account exposure')
    return snapshot


def source_identity(backend):
    hashes=[]
    for name,expected in EXPECTED_SOURCES.items():
        actual=hashlib.sha256((backend/name).read_bytes()).hexdigest()
        if actual!=expected:
            raise ValueError('Installed frozen strategy differs from tested source: '+name)
        hashes.append(actual)
    return hashlib.sha256(''.join(hashes).encode()).hexdigest()


def last_bar_hash(bars):
    return hashlib.sha256(json.dumps(bars[-1],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def evaluate_replay(snapshot):
    """Run the exact frozen V2A class using available-at <= decision-time history.

    Raw broker epochs are provisionally interpreted as UTC for diagnostic replay;
    never authorizes orders or makes a verified-time assertion. Flat-only shadow:
    backtest-style broker-position state is NOT available in this provisional step.
    """
    import pandas as pd
    from app.backtesting.context import StrategyContext,completion_indexes
    from app.backtesting.strategies.mtf_ict_research_v2 import MTFV2ALongOnly
    from app.backtesting.models import EntrySignal
    tf_minutes={'5m':5,'1h':60,'1d':1440}
    frames={}
    for tf,rows in snapshot['bars'].items():
        f=pd.DataFrame(rows).rename(columns={'time':'timestamp'})
        f['timestamp']=pd.to_datetime(f['timestamp'],unit='s',utc=True)
        f['available_at']=f['timestamp']+pd.Timedelta(minutes=tf_minutes[tf])
        frames[tf]=f
    idx=completion_indexes(frames)
    strat=MTFV2ALongOnly();strat.reset()
    results={}
    five=frames['5m'];cutoff=five.iloc[-1]['available_at']
    for row in five.itertuples(index=False):
        decision=row.available_at
        ctx=StrategyContext(symbol='XAUUSD',primary_timeframe='5m',decision_time=decision,
                            frames=frames,position=None,equity=10000.0,
                            completion_indexes=idx)
        result=strat.on_bar(ctx)
        if decision==cutoff and isinstance(result,EntrySignal):
            if result.direction!='long' or result.order_type!='market':
                raise ValueError('Frozen V2A emitted unexpected direction or order type')
            results={'direction':'long','stop_loss':float(result.stop_loss),
                     'target_r':float(result.target_r or 2.0),
                     'reason':result.reason,
                     'level':result.metadata.get('hourly_breakout_level')}
    return results or None


def _database(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(path),timeout=15)
    c.execute('''CREATE TABLE IF NOT EXISTS v2a_frontier (
        identity TEXT PRIMARY KEY, last_m5 INTEGER NOT NULL,
        last_bar_hash TEXT NOT NULL, last_snapshot_hash TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS v2a_shadow_events (
        identity TEXT NOT NULL,m5_time INTEGER NOT NULL,status TEXT NOT NULL,
        document TEXT NOT NULL,PRIMARY KEY(identity,m5_time))''')
    return c


def process(snapshot,backend,db,evaluator=evaluate_replay, identity_fn=source_identity, *, rebase=False):
    validate_snapshot(snapshot)
    sid=identity_fn(backend)
    identity=hashlib.sha256((sid+'|'+snapshot['account_key']+'|'+snapshot['symbol']).encode()).hexdigest()
    bars=snapshot['bars']['5m'];stamp=bars[-1]['time']
    digest=last_bar_hash(bars)
    snap_digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    # Only retain source/config fingerprint, not secret account identifiers.
    with _database(db) as c:
        known=c.execute('SELECT identity FROM v2a_frontier LIMIT 1').fetchone()
        if known is not None and known[0]!=identity:
            raise ValueError('Source, account or symbol identity changed; separate shadow database required')
        previous=c.execute('SELECT last_m5,last_bar_hash FROM v2a_frontier WHERE identity=?',(identity,)).fetchone()
        if previous and stamp==previous[0]:
            if digest!=previous[1]:raise ValueError('Revised completed candle; shadow halted')
            return {'status':'ALREADY_PROCESSED','new_decisions':0,'orders_sent':False}
        if previous and stamp<previous[0]:raise ValueError('Historical clock rollback; shadow halted')
        if previous and stamp-previous[0]!=FIVE_MINUTES and not rebase:
            raise ValueError('Missed completed 5m bar or weekend opening; rebase explicitly in shadow-only mode')
        if previous and not any(row['time']==previous[0] and last_bar_hash([row])==previous[1] for row in bars):
            raise ValueError('Previous confirmed 5m bar revised or evicted; shadow halted')
        # Always re-evaluate from recent completed history; do not restore unserialized strategy state.
        signal=evaluator(snapshot)
        exposed=(snapshot['open_positions']>0 or snapshot['pending_orders']>0)
        if not previous or rebase:
            status='INITIAL_WARMUP_ONLY'
        elif exposed:
            status='BLOCKED_OPEN_ACCOUNT_EXPOSURE'
        elif signal:
            status='PROVISIONAL_LONG_SIGNAL'
        else:
            status='NO_SIGNAL'
        record=dict(status=status,raw_m5_bar_time=stamp,signal=signal if status=='PROVISIONAL_LONG_SIGNAL' else None,
                    no_orders=True,utc_verified=False, source_sha256=sid,
                    note='Provisional raw-broker-time diagnostic, not a trade or fill')
        c.execute('INSERT OR REPLACE INTO v2a_frontier VALUES(?,?,?,?)',(identity,stamp,digest,snap_digest))
        c.execute('INSERT OR IGNORE INTO v2a_shadow_events VALUES(?,?,?,?)',
                  (identity,stamp,status,json.dumps(record,sort_keys=True)))
        return {**record,'orders_sent':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--db',type=Path,default=Path.home()/'.local/share/ledger-v2a-shadow/shadow.sqlite3')
    p.add_argument('--rebase',action='store_true',help='Explicitly reset shadow-only frontier after missed bars; no orders')
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    snapshot=json.loads(args.snapshot.read_text(encoding='utf-8'))
    output=process(snapshot,root,args.db,rebase=args.rebase)
    print(json.dumps(output,indent=2,sort_keys=True,default=str))

if __name__=='__main__':main()
