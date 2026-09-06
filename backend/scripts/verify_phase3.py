import argparse

from app.core.config import get_settings
from app.services.container import build_services
from app.storage.screener_repository import ScreenerFilters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--price-limit", type=int, default=None)
    parser.add_argument("--refresh-fundamentals", action="store_true")
    parser.add_argument("--fundamental-limit", type=int, default=None)
    args = parser.parse_args()

    services = build_services(get_settings())
    try:
        print("Providers:", services.provider_status())
        print("Symbols:", services.symbols.count())
        print("Screener coverage:", services.screener_repository.counts())
        if args.refresh_prices:
            print("Price refresh:", services.screener.refresh_price_snapshots(limit=args.price_limit))
        if args.refresh_fundamentals:
            print("Fundamentals refresh:", services.screener.refresh_bulk_fundamentals(max_companies=args.fundamental_limit))
        total, rows = services.screener.screen(ScreenerFilters(query="AAPL"), limit=5)
        print("AAPL screener check:", total, rows[:1])
        if services.symbols.get("AAPL"):
            print("AAPL research check:", services.research.profile("AAPL"))
    finally:
        services.close()


if __name__ == "__main__":
    main()
