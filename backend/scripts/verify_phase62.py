#!/usr/bin/env python3
"""Small live smoke test for Phase 6.2 provider credentials.

Run from backend/ after filling backend/.env:
    python scripts/verify_phase62.py

It never prints API keys/tokens. It makes a deliberately small number of requests
and reports provider failures without dumping a traceback that could expose secrets.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings
from app.services.container import build_services


def check(services, symbol: str, timeframe: str, days: int) -> None:
    now = datetime.now(timezone.utc)
    frame = services.market_data.get_bars(symbol, timeframe, now - timedelta(days=days), now, force_refresh=True)
    provider = services.market_data.provider_for(symbol)
    print(f"{symbol}: PASS  provider={provider.key}, bars={len(frame)}")
    if not frame.empty:
        print(f"  first={frame.iloc[0]['timestamp']}  last={frame.iloc[-1]['timestamp']}  close={frame.iloc[-1]['close']}")
        if "source_contract" in frame.columns:
            contracts = [x for x in frame["source_contract"].dropna().astype(str).unique().tolist() if x]
            print(f"  source_contracts={', '.join(contracts)}")


def safe_check(services, symbol: str, timeframe: str, days: int) -> bool:
    try:
        check(services, symbol, timeframe, days)
        return True
    except Exception as exc:
        print(f"{symbol}: FAIL")
        print(f"  {type(exc).__name__}: {exc}")
        return False


def main() -> None:
    settings = get_settings()
    services = build_services(settings)
    ok = True
    try:
        if services.market_data is None:
            raise SystemExit("No market-data providers are configured in backend/.env")
        print("Phase 6.2 provider smoke test (credentials are not printed)\n")
        if settings.oanda_configured:
            ok = safe_check(services, "XAUUSD", "5m", 2) and ok
        else:
            print("XAUUSD: SKIP - OANDA_ACCESS_TOKEN is not configured")
        if settings.massive_configured:
            ok = safe_check(services, "NQ1!", "5m", 5) and ok
        else:
            print("NQ1!: SKIP - MASSIVE_API_KEY is not configured")
    finally:
        services.close()

    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
