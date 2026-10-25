#!/usr/bin/env python3
"""Non-trading MT5/TradeQuo V2A diagnostic via Ledger's READ-ONLY bridge.

Never calls order_check/order_send, logs in, switches accounts, writes the
existing Ledger DB, changes bridge settings or enables order execution.

Run from Ledger/backend after its dependencies are installed:
  .venv/bin/python tools/v2a_mt5_readiness.py \
    --token-file "$HOME/.config/ledger-mt5-bridge/token" --confirm-demo
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def record(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return vars(value) if hasattr(value, '__dict__') else None


def collect(client, symbol: str, samples: int = 5, delay: float = 0.7, sleep=time.sleep):
    # This call list is deliberately *only* read-only bridge allowlisted methods.
    before = client.account_info()
    terminal = client.terminal_info()
    metadata = client.symbol_info(symbol)
    quote = client.symbol_info_tick(symbol)
    positions = client.positions_get()
    pending = client.orders_get()
    points = []
    for idx in range(samples):
        points.append(client.tick_diagnostics(symbol))
        if idx < samples - 1:
            sleep(delay)
    after = client.account_info()
    if any(getattr(before, field, None) != getattr(after, field, None)
           for field in ('login', 'server', 'trade_mode', 'currency')):
        raise RuntimeError('Broker account identity changed during observation; NO ACTION TAKEN')

    demo_constant = getattr(client, 'ACCOUNT_TRADE_MODE_DEMO', None)
    demo = (getattr(before, 'trade_mode', None) == demo_constant
            and demo_constant is not None)
    ticks = [p for p in points if isinstance(p, dict)]
    deltas = [number(p.get('raw_minus_receipt_ms')) for p in ticks]
    deltas = [x for x in deltas if x is not None]
    raw_times = [number(p.get('raw_time_msc')) for p in ticks]
    raw_times = [x for x in raw_times if x is not None]
    bid = number(getattr(quote, 'bid', None));ask = number(getattr(quote, 'ask', None))
    spread = (ask-bid if ask is not None and bid is not None and 0 < bid <= ask else None)
    policy = getattr(client, 'timestamp_policy', 'unverified')
    blocks = []
    if not demo:blocks.append('not_confirmed_demo')
    if getattr(terminal, 'connected', False) is not True:blocks.append('terminal_disconnected')
    if not metadata or getattr(metadata, 'name', None) != symbol:blocks.append('symbol_metadata_mismatch')
    if len(positions or []) or len(pending or []):blocks.append('account_has_open_exposure_requires_attribution')
    if policy != 'verified_utc':blocks.append('bridge_history_utc_unverified')
    if len(set(raw_times)) < 2:blocks.append('no_advancing_quotes_observed')
    if not deltas or abs(statistics.median(deltas)) > 5000:blocks.append('raw_tick_clock_differs_from_utc_receipt')
    # Even if this read-only snapshot passes, we have NOT independently verified
    # bar-time and DST correctness and there is NO execution gateway.
    blocks.extend(['historical_bar_utc_and_dst_not_independently_verified',
                   'v2a_completed_bar_worker_not_integrated',
                   'durable_protected_demo_order_gateway_not_integrated'])
    details = {}
    for k in ('trade_contract_size','trade_tick_size','trade_tick_value','volume_min',
              'volume_step','volume_max','point','digits','trade_stops_level',
              'trade_mode','order_mode','filling_mode','trade_exemode'):
        v = getattr(metadata,k,None) if metadata is not None else None
        if type(v) in (int,float,str,bool):details[k]=v
    return {
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'strategy_key':'mtf_v2a_h1_m5_long_only',
        'broker_symbol_requested':symbol,
        'environment':'demo' if demo else 'unverified',
        'account_currency':getattr(before,'currency',None),
        'terminal_connected':getattr(terminal,'connected',None),
        'terminal_trading_permissions':{
            'terminal_trade_allowed':getattr(terminal,'trade_allowed',None),
            'terminal_tradeapi_disabled':getattr(terminal,'tradeapi_disabled',None),
            'account_trade_allowed':getattr(before,'trade_allowed',None),
            'account_trade_expert':getattr(before,'trade_expert',None),
        },
        'broker_symbol_metadata':details,
        'bid':bid,'ask':ask,'quoted_spread_price':spread,
        'quoted_spread_bps':(round(10000*spread/((bid+ask)/2),4) if spread is not None else None),
        'open_positions':len(positions or []),'pending_orders':len(pending or []),
        'bridge_timestamp_policy':policy,
        'tick_sample_count':len(points),
        'advancing_raw_tick_samples':len(set(raw_times)),
        'raw_tick_minus_receipt_ms':{'first':deltas[0] if deltas else None,
                                     'last':deltas[-1] if deltas else None,
                                     'median':statistics.median(deltas) if deltas else None},
        'seasonal_rule_verified':False,
        'blocks_to_resolve':list(dict.fromkeys(blocks)),
        'execution_enabled':False,'orders_sent':False,
        'live_account_modified':False,'existing_database_touched':False,
        'meaning':'Readiness snapshot, NOT authorization to switch UTC policy or submit orders.'
    }


def main():
    parser=argparse.ArgumentParser(description='Read-only V2A demo/clock/contract diagnostic')
    parser.add_argument('--bridge-url',default='http://127.0.0.1:18765')
    parser.add_argument('--token-file',required=True)
    parser.add_argument('--symbol',default='XAUUSDs')
    parser.add_argument('--confirm-demo',required=True,action='store_true')
    parser.add_argument('--output',type=Path,help='Optional path for sanitized JSON report')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    from app.brokers.mt5_bridge_client import BridgeClient
    client=BridgeClient(args.bridge_url,args.token_file,'demo')
    try:
        client.initialize()
        report=collect(client,args.symbol)
    except Exception:
        print('MT5 readiness probe failed. Confirm demo terminal/bridge is connected; NO orders were sent.',file=sys.stderr)
        return 2
    finally:
        try:client.shutdown()
        except Exception:pass
    serialized=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(serialized+'\n',encoding='utf-8')
    return 0


if __name__=='__main__':raise SystemExit(main())
