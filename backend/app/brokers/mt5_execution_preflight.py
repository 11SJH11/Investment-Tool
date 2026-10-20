"""Read-only demo entry preflight. Passing is never submission authorization.

The caller must own the existing terminal lifecycle/profile locks. Quotes and
account facts must be rechecked by the eventual gateway immediately before send.
No order_check/order_send API is called here.
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_sizing import estimate, finite


class DemoEntryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str = Field(min_length=1, max_length=256)
    side: Literal['buy', 'sell']
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    risk_percent: float = Field(gt=0, le=100)


def preflight(adapter, request, *, now_ms, max_quote_age_ms=5000):
    """Use executable ask/bid and broker calculations, without placing an order.

    Five seconds is a local safety bound, not a broker promise. Account-wide
    exposure, session limits and durable authorization remain separate gates.
    """
    try:
        request = DemoEntryRequest.model_validate(request)
        finite(now_ms, positive=True)
        finite(max_quote_age_ms, positive=True)
        account, key = adapter._account()
        module = adapter._module
        if adapter.environment != 'demo' or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('demo_required')
        if key != adapter.account_key or account.currency != adapter.currency:
            raise ValueError('account_changed')
        terminal = module.terminal_info()
        if (terminal is None or terminal.connected is not True or terminal.trade_allowed is not True
                or terminal.tradeapi_disabled is not False or account.trade_allowed is not True
                or account.trade_expert is not True):
            raise ValueError('trading_permissions_unavailable')
        info = module.symbol_info(request.symbol)
        if info is None or info.name != request.symbol:
            raise ValueError('unknown_symbol')
        allowed_modes = {module.SYMBOL_TRADE_MODE_FULL,
                         module.SYMBOL_TRADE_MODE_LONGONLY if request.side == 'buy'
                         else module.SYMBOL_TRADE_MODE_SHORTONLY}
        # Official SYMBOL_ORDER_MODE bit flags. MetaTrader5 Python exposes
        # order_mode but does not export these MQL5 symbol flag constants.
        required_orders = 1 | 16 | 32  # MARKET | SL | TP
        if info.trade_mode not in allowed_modes or info.order_mode & required_orders != required_orders:
            raise ValueError('protected_market_entry_unsupported')
        quote = module.symbol_info_tick(request.symbol)
        if quote is None:
            raise ValueError('quote_unavailable')
        stamp = finite(quote.time_msc, positive=True)
        if not 0 <= now_ms - stamp <= max_quote_age_ms:
            raise ValueError('stale_or_future_quote')
        bid, ask = (finite(quote.bid, positive=True), finite(quote.ask, positive=True))
        if ask < bid:
            raise ValueError('crossed_quote')
        entry = ask if request.side == 'buy' else bid
        if not (request.stop < entry < request.target if request.side == 'buy'
                else request.target < entry < request.stop):
            raise ValueError('invalid_stop_target')
        tick = Decimal(str(finite(info.trade_tick_size, positive=True)))
        if any(Decimal(str(p)) % tick for p in (entry, request.stop, request.target)):
            raise ValueError('price_tick_alignment')
        points = finite(info.trade_stops_level)
        if points < 0 or not points.is_integer():
            raise ValueError('invalid_stop_distance')
        distance = Decimal(str(points)) * Decimal(str(finite(info.point, positive=True)))
        # Long protections trigger against bid, shorts against ask, not entry.
        reference = Decimal(str(bid if request.side == 'buy' else ask))
        stop, target = Decimal(str(request.stop)), Decimal(str(request.target))
        gaps = (reference-stop, target-reference) if request.side == 'buy' else (stop-reference, reference-target)
        if any(gap <= 0 or gap < distance for gap in gaps):
            raise ValueError('broker_stop_distance')
        sizing = estimate(adapter, dict(symbol=request.symbol, side=request.side, entry=entry,
                                        stop=request.stop, risk_percent=request.risk_percent))
        if sizing['rejection_reason']:
            raise ValueError(sizing['rejection_reason'])
        final_account, final_key = adapter._account()
        if (final_key != key or adapter.account_key != key or adapter.environment != 'demo'
                or final_account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or final_account.currency != account.currency or adapter.currency != account.currency):
            raise ValueError('account_changed')
        return dict(sizing=sizing, target=request.target, bid=bid, ask=ask,
                    quote_time_msc=stamp, spread=ask-bid, execution_enabled=False,
                    status='read_only_preflight_passed',
                    remaining_gates=['account_wide_risk', 'durable_authorization',
                                     'reconciliation', 'broker_submission_and_protection_verification'])
    except Exception:
        # Never propagate terminal exception strings, credentials or raw accounts.
        raise BrokerHistoryError('MT5 demo entry preflight rejected; verify demo identity, permissions, fresh quotes, stops and sizing',
                                 category='configuration') from None
