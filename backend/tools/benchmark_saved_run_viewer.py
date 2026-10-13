"""Opt-in synthetic saved-run API for browser profiling; no settings/provider access.

Run from backend: python -B tools/benchmark_saved_run_viewer.py --directory <new-dir>
Browser: LEDGER_BENCHMARK_API=http://127.0.0.1:19384
"""
import argparse
import gc
import json
import math
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True)
    parser.add_argument('--port',type=int,default=19384);args=parser.parse_args()
    root=Path(args.directory).resolve();root.mkdir(parents=True,exist_ok=False)
    db=Database(root/'synthetic.db');db.initialize();repo=BacktestRunRepository(db)
    epoch=datetime(2020,1,2,14,30,tzinfo=timezone.utc)
    stamp=lambda i:(epoch+timedelta(minutes=i)).isoformat()
    trades=[dict(symbol='QQQ',direction='long',entry_time=stamp(i*220),exit_time=stamp(i*220+30),
        entry_price=100,exit_price=101,net_pnl=10,r_multiple=1,result='win',exit_reason='strategy_exit',metadata={'evidence':'x'*500}) for i in range(3000)]
    curve=[dict(timestamp=stamp(i),equity=100000+i*.01+math.sin(i/30)*100,return_pct=i*.00001,
        drawdown_pct=-abs(math.sin(i/30)),cumulative_r=i*.0001) for i in range(660000)]
    for i,t in enumerate(trades):curve[i*220+30]['closed_trades']=[{k:t[k] for k in ('symbol','exit_time','exit_reason')}]
    result=dict(strategy={'key':'heavy_fixture','name':'Heavy fixture'},symbols=['QQQ'],
        metrics={'trades':3000,'starting_balance':100000,'ending_balance':106600},
        equity_curve=curve,trades=trades,analysis={'diagnostics':['x'*500]*3000},execution_model={})
    repo.create(config={'strategy_key':'heavy_fixture','symbols':['QQQ'],'starting_balance':100000},result=result)
    del result,curve,trades;gc.collect()
    measurements=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            started=perf_counter()
            try:
                section=self.path.rsplit('/',1)[-1]
                if section=='measurements':value=measurements
                else:value=repo.get_section(1,section)
                read=perf_counter();body=json.dumps(value,separators=(',',':')).encode();serialized=perf_counter()
                if section!='measurements':
                    measurements.append(dict(section=section,read_decode_ms=(read-started)*1000,
                        serialize_ms=(serialized-read)*1000,bytes=len(body)))
                    (root/'measurements.json').write_text(json.dumps(measurements,indent=2))
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Access-Control-Allow-Origin','*');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            except (ValueError,KeyError):self.send_error(404)
    print(f'Synthetic benchmark ready on 127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()


if __name__=='__main__':main()
