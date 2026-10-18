
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone

if not mt5.initialize():
    print("Connection failed:", mt5.last_error())
    raise SystemExit

try:
    account = mt5.account_info()
    terminal = mt5.terminal_info()

    print("Account:", account.login)
    print("Server:", account.server)
    print("Terminal path:", terminal.path)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    deals = mt5.history_deals_get(start, end)
    print("\nDeals:", None if deals is None else len(deals))
    print("Deal lookup error:", mt5.last_error())

    orders = mt5.history_orders_get(start, end)
    print("\nHistorical orders:", None if orders is None else len(orders))
    print("Order lookup error:", mt5.last_error())

    if orders:
        for order in orders:
            print(
                "Order:", order.ticket,
                "Symbol:", order.symbol,
                "Position:", order.position_id,
                "State:", order.state
            )
finally:
    mt5.shutdown()
