"""Bounded read-only account-wide observations for the demo execution gateway.

Caller owns the existing MT5 terminal/profile locks. This is not broker/ledger
reconciliation and never returns reconciled=True or submits an order. Unsupported
valuation, missing protection or changing broker structure fails closed.
"""
from datetime import datetime, timezone
from decimal import Decimal

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_execution_risk import AccountRiskFacts
from app.brokers.mt5_sizing import finite


def gross_exposure(module, symbol, volume, price, currency):
    """Same-currency linear contracts only; no guessed FX/futures conversion."""
    info = module.symbol_info(symbol)
    modes = {module.SYMBOL_CALC_MODE_FOREX, module.SYMBOL_CALC_MODE_CFD}
    if (info is None or info.name != symbol or info.currency_profit != currency
            or info.trade_calc_mode not in modes):
        raise ValueError('unsupported_exposure_valuation')
    values = (volume, price, info.trade_contract_size)
    result = Decimal(1)
    for value in values:
        result *= Decimal(str(finite(value, positive=True)))
    return finite(float(result), positive=True)


def observe(adapter, *, strategy_key, session_key, session_entries, unresolved_submissions):
    """Observe all account trades, including manual/other-strategy exposure.

    Session/uncertainty counts must come from the durable gateway, not the UI.
    Gross losses include each negative fee/swap/commission separately. Deposits
    and withdrawals are excluded. Separate unsupported cash operations reject
    instead of silently disappearing. New reconciliation must follow observation.
    """
    try:
        module = adapter._module
        now_ms = int(adapter._clock() * 1000)
        start = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        account, key = adapter._account()
        if (adapter.environment != 'demo' or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or key != adapter.account_key or account.currency != adapter.currency):
            raise ValueError('account_identity')

        def rows(value, fields, limit=10000):
            if value is None or len(value) >= limit:
                raise ValueError('incomplete_broker_rows')
            result = []
            for row in value:
                item = {field: getattr(row, field) for field in fields}
                for field, val in item.items():
                    if field == 'symbol':
                        if not isinstance(val, str) or not val or len(val) > 256:
                            raise ValueError('invalid_symbol')
                    else:
                        finite(val)
                if type(item['ticket']) is not int or item['ticket'] <= 0:
                    raise ValueError('invalid_ticket')
                result.append(item)
            if len({row['ticket'] for row in result}) != len(result):
                raise ValueError('duplicate_ticket')
            return sorted(result, key=lambda row: row['ticket'])

        pfields = ('ticket', 'symbol', 'type', 'volume', 'sl', 'tp', 'swap')
        ofields = ('ticket', 'symbol', 'type', 'volume_current', 'price_open', 'sl', 'tp')
        dfields = ('ticket', 'type', 'time_msc', 'profit', 'commission', 'swap', 'fee')
        positions = rows(module.positions_get(), pfields)
        orders = rows(module.orders_get(), ofields)
        end = datetime.fromtimestamp(now_ms / 1000, timezone.utc)
        deals = rows(module.history_deals_get(start, end), dfields, 100000)
        losses = floating = remaining = exposure = pending_exposure = pending_risk = 0.
        def stop_risk(side, symbol, volume, price, stop):
            result = finite(module.order_calc_profit(side, symbol, volume, price, stop))
            if result >= 0:
                raise ValueError('invalid_broker_stop_calculation')
            return -result
        for deal in deals:
            if not int(start.timestamp()*1000) <= deal['time_msc'] <= now_ms:
                raise ValueError('history_outside_window')
            if deal['type'] not in {module.DEAL_TYPE_BUY, module.DEAL_TYPE_SELL,
                                    module.DEAL_TYPE_BALANCE, module.DEAL_TYPE_CREDIT}:
                raise ValueError('unsupported_cash_operation')
            fields = ('commission', 'swap', 'fee')
            if deal['type'] in {module.DEAL_TYPE_BUY, module.DEAL_TYPE_SELL}:
                fields += ('profit',)
            losses += sum(max(0., -deal[field]) for field in fields)

        for position in positions:
            side = position['type']
            if side not in {module.ORDER_TYPE_BUY, module.ORDER_TYPE_SELL}:
                raise ValueError('unknown_position_side')
            quote = module.symbol_info_tick(position['symbol'])
            if quote is None or not 0 <= now_ms - finite(quote.time_msc, positive=True) <= 5000:
                raise ValueError('stale_quote')
            bid, ask = finite(quote.bid, positive=True), finite(quote.ask, positive=True)
            if ask < bid:
                raise ValueError('crossed_quote')
            price = bid if side == module.ORDER_TYPE_BUY else ask
            stop = finite(position['sl'], positive=True)
            if not (stop < price if side == module.ORDER_TYPE_BUY else stop > price):
                raise ValueError('stop_already_crossed')
            exposure += gross_exposure(module, position['symbol'], position['volume'], max(bid, ask), account.currency)
            remaining += stop_risk(side, position['symbol'], position['volume'], price, stop)
            # Native current profit is account-currency; never offset losing
            # positions with winners. Re-read structural state below.
        # Profit requires its own allowlisted read paired with structural facts.
        current = module.positions_get()
        if rows(current, pfields) != positions:
            raise ValueError('positions_changed')
        floating = sum(max(0., -finite(p.profit)) + max(0., -finite(p.swap)) for p in current)

        pending_sides = {module.ORDER_TYPE_BUY_LIMIT: module.ORDER_TYPE_BUY,
                         module.ORDER_TYPE_BUY_STOP: module.ORDER_TYPE_BUY,
                         module.ORDER_TYPE_SELL_LIMIT: module.ORDER_TYPE_SELL,
                         module.ORDER_TYPE_SELL_STOP: module.ORDER_TYPE_SELL}
        for order in orders:
            if order['type'] not in pending_sides:
                raise ValueError('unsupported_pending_order')
            side = pending_sides[order['type']]
            price, stop = finite(order['price_open'], positive=True), finite(order['sl'], positive=True)
            if not (stop < price if side == module.ORDER_TYPE_BUY else stop > price):
                raise ValueError('invalid_pending_stop')
            pending_exposure += gross_exposure(module, order['symbol'], order['volume_current'], price, account.currency)
            pending_risk += stop_risk(side, order['symbol'], order['volume_current'], price, stop)

        finish_ms = int(adapter._clock() * 1000)
        final_account, final_key = adapter._account()
        if (not 0 <= finish_ms-now_ms <= 5000 or final_key != key or adapter.account_key != key
                or final_account.currency != account.currency or adapter.currency != account.currency
                or adapter.environment != 'demo' or final_account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO):
            raise ValueError('account_changed_or_observation_expired')
        if (rows(module.positions_get(), pfields) != positions or rows(module.orders_get(), ofields) != orders
                or rows(module.history_deals_get(start, datetime.fromtimestamp(finish_ms/1000, timezone.utc)), dfields, 100000) != deals):
            raise ValueError('broker_state_changed')
        return AccountRiskFacts(account_key=key, environment='demo', currency=account.currency,
            observed_at_ms=now_ms, complete=True, reconciled=False, risk_day_utc=start.date().isoformat(),
            session_key=session_key, strategy_key=strategy_key, session_entries=session_entries,
            unresolved_submissions=unresolved_submissions,
            equity=min(finite(account.equity, positive=True), finite(final_account.equity, positive=True)),
            free_margin=min(finite(account.margin_free), finite(final_account.margin_free)),
            open_positions=len(positions), pending_entries=len(orders), gross_exposure=exposure,
            pending_gross_exposure=pending_exposure, realized_losses_today=losses,
            floating_losses=floating, remaining_stop_risk=remaining, pending_stop_risk=pending_risk).model_dump()
    except Exception:
        raise BrokerHistoryError('MT5 risk observation unavailable: verify account, protected positions, supported valuation and complete stable history',
                                 category='history') from None
