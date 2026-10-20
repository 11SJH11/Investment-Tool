"""Prepare and broker-check a protected demo request. Never calls order_send.

This does not authorize execution or replace account-wide risk/reconciliation.
The caller owns the terminal/profile locks. A request must be freshly prepared
again under the durable account guard before a future authorized submission.
"""
from hashlib import sha256

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_execution_preflight import preflight
from app.brokers.mt5_sizing import finite


def prepare(adapter, entry, *, intent_id, magic, deviation_points):
    from app.research_agent.access import active
    if active():
        raise BrokerHistoryError('Research cannot prepare broker execution requests', category='configuration')
    try:
        if (not isinstance(intent_id, str) or not 1 <= len(intent_id) <= 128
                or type(magic) is not int or not 1 <= magic <= 2147483647
                or type(deviation_points) is not int or not 0 <= deviation_points <= 1000):
            raise ValueError('invalid_request_identity')
        now_ms = int(adapter._clock()*1000)
        checked = preflight(adapter, entry, now_ms=now_ms)
        sizing = checked['sizing']
        module = adapter._module
        info = module.symbol_info(sizing['symbol'])
        if info is None or info.name != sizing['symbol']:
            raise ValueError('symbol_changed')
        # Prefer all-or-none when advertised; IOC supports partial-fill recovery.
        # Do not use RETURN or leave a residual working entry order by default.
        # SYMBOL_FILLING_* flags (1=FOK, 2=IOC) are not exported by the
        # official Python package; ORDER_FILLING_* request enums are.
        if info.filling_mode & 1:
            filling = module.ORDER_FILLING_FOK
        elif info.filling_mode & 2:
            filling = module.ORDER_FILLING_IOC
        else:
            raise ValueError('unsupported_fill_policy')
        modes = {module.SYMBOL_TRADE_EXECUTION_REQUEST, module.SYMBOL_TRADE_EXECUTION_INSTANT,
                 module.SYMBOL_TRADE_EXECUTION_MARKET, module.SYMBOL_TRADE_EXECUTION_EXCHANGE}
        if info.trade_exemode not in modes:
            raise ValueError('unknown_execution_mode')
        request = dict(action=module.TRADE_ACTION_DEAL, symbol=sizing['symbol'],
                       volume=sizing['quantity_lots'],
                       type=module.ORDER_TYPE_BUY if sizing['side'] == 'buy' else module.ORDER_TYPE_SELL,
                       sl=sizing['stop'], tp=checked['target'], deviation=deviation_points,
                       magic=magic, comment='Ledger-'+sha256(intent_id.encode()).hexdigest()[:20],
                       type_time=module.ORDER_TIME_GTC, type_filling=filling)
        if info.trade_exemode != module.SYMBOL_TRADE_EXECUTION_MARKET:
            request['price'] = sizing['entry']
        account, key = adapter._account()
        if (adapter.environment != 'demo' or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or key != sizing['account_key'] or key != adapter.account_key):
            raise ValueError('account_changed')
        result = module.order_check(dict(request))
        if result is None or type(result.retcode) is not int:
            raise ValueError('broker_check_unavailable')
        account, key = adapter._account()
        finish_ms = int(adapter._clock()*1000)
        if (key != sizing['account_key'] or adapter.account_key != key
                or adapter.environment != 'demo' or account.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                or account.currency != sizing['currency'] or adapter.currency != sizing['currency']
                or not 0 <= finish_ms-checked['quote_time_msc'] <= 5000):
            raise ValueError('account_changed_or_expired')
        passed = result.retcode == 0
        if passed and finite(result.margin_free) < 0:
            raise ValueError('negative_broker_free_margin')
        return dict(status='broker_check_passed' if passed else 'broker_check_rejected',
                    broker_retcode=result.retcode, request=request, preflight=checked,
                    execution_enabled=False, orders_sent=False,
                    warning='Broker check only; not an accepted order or execution authorization.')
    except Exception:
        # Raw native error/comment/request echoes can contain private details.
        raise BrokerHistoryError('MT5 demo order preparation failed; verify broker permissions, fill policy, account and fresh prices',
                                 category='configuration') from None
