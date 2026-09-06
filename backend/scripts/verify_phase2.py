"""Optional live smoke test for the Phase 2 data layer.

Run from backend/ after configuring .env:
    python scripts/verify_phase2.py
    python scripts/verify_phase2.py --refresh-symbols --live
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.services.container import build_services  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-symbols", action="store_true")
    parser.add_argument("--live", action="store_true", help="Make sample external API calls")
    args = parser.parse_args()

    services = build_services(get_settings())
    try:
        print("Provider status:")
        for name, status in services.provider_status().items():
            print(f"  {name:7} {'configured' if status['configured'] else 'not configured'}")
        print(f"Cached symbols: {services.symbols.count():,}")

        if args.refresh_symbols:
            if services.symbol_universe is None:
                print("No security-master provider configured.")
            else:
                result = services.symbol_universe.refresh()
                print(f"Refreshed {result['symbols']:,} symbols from {result['source']}.")
                if result.get("cik_matches"):
                    print(f"SEC CIK matches: {result['cik_matches']:,}")

        if not args.live:
            return 0

        if services.market_data is not None:
            delay = services.settings.alpaca_historical_delay_minutes
            end = datetime.now(timezone.utc) - timedelta(minutes=delay + 1)
            start = end - timedelta(days=10)
            bars = services.market_data.get_bars("AAPL", "1d", start, end)
            print(f"AAPL daily bars: {len(bars):,}")
        else:
            print("Skipping Alpaca bar check: not configured.")

        if services.fundamentals is not None:
            data = services.fundamentals.get("AAPL")
            print(f"SEC AAPL: {data.get('company_name')} | revenue={data.get('revenue')}")
        else:
            print("Skipping SEC fundamentals check: SEC_USER_AGENT not configured.")

        if services.macro is not None:
            snapshot = services.macro.get_snapshot()
            print(f"FRED series loaded: {', '.join(snapshot)}")
        else:
            print("Skipping FRED check: FRED_API_KEY not configured.")
        return 0
    finally:
        services.close()


if __name__ == "__main__":
    raise SystemExit(main())
