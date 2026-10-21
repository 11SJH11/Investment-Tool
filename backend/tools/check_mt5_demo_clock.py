"""Opt-in read-only probe of an already logged-in, explicitly selected demo terminal.

No .env/login/password loading, account switching, symbol selection or order APIs.
Prints only allowlisted samples/permissions, never account login or native errors.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.brokers.mt5_clock_diagnostic import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terminal-path', required=True)
    parser.add_argument('--symbol', required=True)
    args = parser.parse_args()
    path = Path(args.terminal_path).resolve(strict=True)
    if path.name.lower() != 'terminal64.exe':
        parser.error('Select the exact terminal64.exe path')
    result = dict(status='verification_unavailable', execution_enabled=False, orders_sent=False)
    module = None
    try:
        import MetaTrader5 as module
        if not module.initialize(path=str(path), timeout=10000):
            raise ValueError()
        terminal, account = module.terminal_info(), module.account_info()
        if (terminal is None or account is None or not terminal.connected
                or Path(terminal.path).resolve() != path.parent
                or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO):
            raise ValueError()
        samples = []
        for i in range(5):
            tick = module.symbol_info_tick(args.symbol)
            receipt = time.time()*1000
            if tick is None:
                raise ValueError()
            samples.append(dict(receipt_ms=receipt, tick_ms=tick.time_msc))
            if i < 4:
                time.sleep(1)
        final = module.account_info()
        if final is None or (final.login,final.server,final.trade_mode) != (account.login,account.server,account.trade_mode):
            raise ValueError()
        result = dict(**summarize(samples), samples=samples, orders_sent=False,
                      terminal_algo_trading=terminal.trade_allowed,
                      python_api_allowed=not terminal.tradeapi_disabled,
                      account_expert_trading=account.trade_expert)
    except Exception:
        pass  # Native exception strings/last_error can contain private details.
    finally:
        if module is not None:
            try: module.shutdown()
            except Exception: pass
    print(json.dumps(result))
    return 0 if result['status'] == 'current_offset_observed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
