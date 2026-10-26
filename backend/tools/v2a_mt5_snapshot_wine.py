"""PROVISIONAL read-only MT5 5m/1h/1d snapshot under Wine Windows Python.

No order endpoints, trade operations, login credentials, policy changes, or UTC claims.
Uses existing demo terminal path/account pin in the local bridge configuration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time


def build_snapshot(module, config, symbol, *, at=None, counts=None):
    counts = counts or {'5m': 2500, '1h': 250, '1d': 45}
    if config.get('environment') != 'demo':
        raise ValueError('DEMO configuration required')
    account = module.account_info()
    term = module.terminal_info()
    if (account is None or term is None or not term.connected or
        account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO or
        account.login != config['expected_login'] or
        account.server != config['expected_server']):
        raise ValueError('Pinned demo terminal/account not available')
    info = module.symbol_info(symbol)
    if info is None or info.name != symbol or not info.visible:
        raise ValueError('The exact Gold symbol must already be visible in MT5')
    specs = [('5m', module.TIMEFRAME_M5), ('1h', module.TIMEFRAME_H1), ('1d', module.TIMEFRAME_D1)]
    output = {}
    for name, tf in specs:
        raw = module.copy_rates_from_pos(symbol, tf, 1, counts[name])
        if raw is None or len(raw) < min(counts[name], {'5m': 300, '1h': 18, '1d': 26}[name]):
            raise ValueError('Insufficient completed broker chart candles for '+name)
        rows = []
        for r in raw:
            item = {'time': int(r['time']),
                    'open': float(r['open']), 'high': float(r['high']),
                    'low': float(r['low']), 'close': float(r['close']),
                    'volume': float(r['tick_volume'])}
            rows.append(item)
        rows.sort(key=lambda r:r['time'])
        if len({r['time'] for r in rows}) != len(rows):
            raise ValueError('Duplicate bar timestamp')
        output[name] = rows
    tick = module.symbol_info_tick(symbol)
    positions = module.positions_get()
    pending = module.orders_get()
    after = module.account_info()
    if (tick is None or positions is None or pending is None or after is None or
        after.login != account.login or after.server != account.server or
        after.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO):
        raise ValueError('Incomplete snapshot or account changed')
    # Hash for consistency only; do not disclose account number or server.
    account_key = hashlib.sha256(('%s|%s|%s' % (account.login, account.server, account.currency)).encode()).hexdigest()
    return dict(format='ledger-v2a-provisional-mt5-snapshot-v1',
                strategy_key='mtf_v2a_h1_m5_long_only', symbol=symbol,
                account_key=account_key, environment='demo',
                timestamp_contract='UNVERIFIED_RAW_BROKER_EPOCH',
                captured_at_epoch=int(at if at is not None else time.time()),
                last_tick_raw_msc=int(tick.time_msc),
                bid=float(tick.bid),ask=float(tick.ask),
                account_currency=account.currency,
                open_positions=len(positions), pending_orders=len(pending),bars=output,
                orders_sent=False,execution_enabled=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True,help='Existing LOCAL read-only bridge config.json')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--symbol',default='XAUUSDs')
    p.add_argument('--confirm-demo',action='store_true',required=True)
    args=p.parse_args()
    config=json.loads(args.config.read_text(encoding='utf-8'))
    if config.get('environment')!='demo':p.error('Demo bridge config required')
    import MetaTrader5 as mt5
    if not mt5.initialize(config['terminal_path'],timeout=30000):
        raise SystemExit('Pinned MT5 demo terminal not available. Nothing changed.')
    try:
        snapshot=build_snapshot(mt5,config,args.symbol)
    finally:
        mt5.shutdown()
    path=args.out.expanduser();path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp-'+str(os.getpid()))
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    fd=os.open(str(temp),flags,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(snapshot,f,allow_nan=False,separators=(',',':'))
            f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    print('Read-only completed bar snapshot saved:',path)
    print('MT5 orders sent: false | Timestamp contract: UNVERIFIED | Symbol:',args.symbol)

if __name__=='__main__':main()
