"""Opt-in genuine cached Gold baseline. No services, credentials, downloads or user DB writes.

Uses a selected campaign's original development/warmup configuration and deadline
allocation with current registered code. Writes a separate managed verification
artifact; never resumes or changes the original campaign or claims its provenance.
"""
import argparse
from datetime import datetime, time as day_time, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-id',required=True)
    args=parser.parse_args()
    with sqlite3.connect((ROOT/'data/ledger.db').as_uri()+'?mode=ro',uri=True) as c:
        c.execute('PRAGMA query_only=ON')
        raw=c.execute('SELECT document FROM agent_campaigns WHERE id=?',(args.campaign_id,)).fetchone()
        if not raw:raise ValueError('Campaign not found')
        campaign=json.loads(raw[0])
        entries=campaign.get('execution',{}).get('entries',[])
        if len(entries)!=1:raise ValueError('Select a single-family Gold campaign')
        entry=entries[0];payload=dict(entry['payload']);plan=campaign['plans'][entry['plan_key']]
        if payload['strategy_key']!='gold_asia_15m_ifvg_research_v1' or payload['symbols']!=['XAUUSD']:
            raise ValueError('This verifier is restricted to the existing Gold baseline')
        if (payload['start_date']!=plan['development']['start'] or payload['end_date']!=plan['development']['end']
                or payload['warmup_start_date']!=plan['warmup']['start']):
            raise ValueError('Configuration differs from the declared development plan')
        for row in c.execute('SELECT document FROM agent_datasets'):
            d=json.loads(row[0])
            if ('XAUUSD' in d['symbols'] and d['state'] in {'LOCKED_HOLDOUT','FUTURE_OOS','INSPECTED_VALIDATION'}
                    and payload['warmup_start_date']<=d['end'] and d['start']<=payload['end_date']):
                raise ValueError('Development verification overlaps protected/validation history')
    from app.services.backtest import BacktestService
    from app.research_agent.analysis import digest,summary
    import duckdb
    zone=ZoneInfo('America/New_York')
    begin=datetime.combine(datetime.fromisoformat(payload['warmup_start_date']).date(),day_time.min,zone)
    end=datetime.combine(datetime.fromisoformat(payload['end_date']).date()+timedelta(days=1),day_time.min,zone)
    namespace=plan['coverage']['provider_namespace']
    if namespace!='oanda-mid-v1':raise ValueError('Expected original OANDA midpoint history')
    files={}
    class CachedOnly:
        provider=SimpleNamespace(key='oanda',cache_namespace=namespace)
        def get_bars(self,symbol,timeframe,start,finish):
            if symbol!='XAUUSD' or timeframe not in {'1m','15m'} or start<begin or finish>end:
                raise ValueError('Request exceeds frozen development bounds')
            path=ROOT/'data/market/bars'/namespace/timeframe/'XAUUSD.parquet'
            before=path.stat()
            with duckdb.connect() as connection:
                frame=connection.execute('SELECT * FROM read_parquet(?) WHERE timestamp>=? AND timestamp<? ORDER BY timestamp',
                    [str(path),start,finish]).df()
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                raise ValueError('Cache changed during bounded read')
            if frame.empty:raise ValueError('Required cached history is empty')
            files[timeframe]=dict(bytes=before.st_size,mtime_ns=before.st_mtime_ns,rows=len(frame))
            return frame
    output=ROOT/'data/research_verification'/('gold-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();limit=entry['max_minutes']*60
    if not 0<limit<=7200:raise ValueError('Invalid bounded campaign allocation')
    last=0
    def write(name,document):
        temp=output/(name+'.tmp');temp.write_text(json.dumps(document,default=str,allow_nan=False),encoding='utf-8');temp.replace(output/name)
    manifest=dict(campaign_id=args.campaign_id,original_status=campaign['status'],configuration=payload,
        source='current_corrected_implementation',deadline_seconds=limit,provider=namespace,
        user_database_read_only=True,provider_calls=0,holdout_access=False,output=str(output))
    write('manifest.json',manifest)
    def progress(phase,done,total):
        nonlocal last
        elapsed=time.monotonic()-started
        if elapsed>=limit:raise TimeoutError('Original campaign compute allocation exceeded')
        if elapsed-last>=2 or phase!='running':
            write('progress.json',dict(status='RUNNING',phase=phase,processed=done,total=total,elapsed_seconds=elapsed))
            last=elapsed
    try:
        result=BacktestService(CachedOnly()).run({**payload,'save_run':False},progress=progress)
        elapsed=time.monotonic()-started
        if elapsed>=limit:raise TimeoutError('Original campaign compute allocation exceeded')
        write('result.json',result)
        manifest.update(status='COMPLETED',elapsed_seconds=elapsed,files=files,
            result_sha256=digest(result),summary=summary(result['trades']),
            data=result.get('data'),implementation=result['strategy']['implementation'])
        write('manifest.json',manifest);write('progress.json',dict(status='COMPLETED',elapsed_seconds=elapsed))
        print(json.dumps({k:manifest[k] for k in ('status','elapsed_seconds','output','summary')}),flush=True)
    except BaseException as exc:
        manifest.update(status='FAILED',elapsed_seconds=time.monotonic()-started,error_type=type(exc).__name__)
        write('manifest.json',manifest);write('progress.json',dict(status='FAILED',error_type=type(exc).__name__))
        raise


if __name__=='__main__':main()
