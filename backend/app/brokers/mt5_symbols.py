"""Current broker metadata, never a synthetic futures/security master."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import math

from app.brokers.base import BrokerHistoryError


TEXT_FIELDS = ('name', 'description', 'path', 'exchange', 'currency_base',
               'currency_profit', 'currency_margin', 'isin')
NUMBER_FIELDS = ('digits', 'point', 'trade_tick_size', 'trade_tick_value',
                 'trade_tick_value_profit', 'trade_tick_value_loss', 'trade_contract_size',
                 'volume_min', 'volume_max', 'volume_step', 'volume_limit',
                 'trade_calc_mode', 'trade_mode', 'margin_initial', 'margin_maintenance',
                 'margin_hedged', 'start_time', 'expiration_time', 'spread', 'time',
                 'bid', 'ask', 'session_open', 'session_close')
BOOL_FIELDS = ('custom', 'select', 'visible', 'spread_float', 'margin_hedged_use_leg')


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def symbol_metadata(info, module, account_key, environment):
    item = {}
    for field in TEXT_FIELDS:
        value = getattr(info, field, None)
        item[field] = value if isinstance(value, str) else None
    if not item['name'] or len(item['name']) > 256:
        raise BrokerHistoryError('MetaTrader 5 returned invalid symbol metadata', category='history')
    for field in NUMBER_FIELDS:
        value = getattr(info, field, None)
        item[field] = value if isinstance(value, (int, float)) and math.isfinite(value) else None
    for field in BOOL_FIELDS:
        value = getattr(info, field, None)
        item[field] = value if isinstance(value, bool) else None
    mode = item['trade_calc_mode']
    kind = 'unknown'
    # Calculation modes are provider facts; names/path alone are not evidence.
    for label, names in (
        ('forex', ('FOREX', 'FOREX_NO_LEVERAGE')),
        ('cfd', ('CFD', 'CFDINDEX', 'CFDLEVERAGE')),
        ('broker_future_unverified', ('FUTURES', 'EXCH_FUTURES', 'EXCH_FUTURES_FORTS')),
        ('exchange_stock', ('EXCH_STOCKS', 'EXCH_STOCKS_MOEX')),
    ):
        if mode is not None and any(mode == getattr(module, 'SYMBOL_CALC_MODE_' + name, object()) for name in names):
            kind = label
    item.update(provider='mt5', environment=environment, account_key=account_key,
                instrument_type=kind, canonical_symbol=None, futures_verified=False,
                instrument_id=fingerprint(['mt5', environment, account_key, item['name']]),
                metadata_basis='current_terminal_symbol_info_not_historical',
                trading_sessions=None,
                trading_sessions_status='not_exposed_by_python_symbol_info')
    item['metadata_fingerprint'] = fingerprint(item)
    return item


def read_catalog(adapter):
    """Caller owns the existing terminal lock through adapter.connect/close."""
    if not adapter.account_key:
        raise BrokerHistoryError('Connect an MT5 account before discovery', category='configuration')
    try:
        rows = adapter._module.symbols_get()
        if rows is None or len(rows) > 100000:
            raise BrokerHistoryError('MetaTrader 5 symbol discovery failed or exceeds the safe budget', category='history')
        items = [symbol_metadata(row, adapter._module, adapter.account_key, adapter.environment) for row in rows]
        if len({item['name'] for item in items}) != len(items):
            raise BrokerHistoryError('MetaTrader 5 returned duplicate symbol names', category='history')
        if adapter._account()[1] != adapter.account_key:
            raise BrokerHistoryError('MetaTrader 5 account changed during symbol discovery', category='connection')
        items.sort(key=lambda item: item['name'])
        return dict(provider='mt5', environment=adapter.environment, account_key=adapter.account_key,
                    observed_at=datetime.now(timezone.utc).isoformat(), items=items,
                    fingerprint=fingerprint(items), schema_version=1)
    except BrokerHistoryError:
        raise
    except Exception:
        raise BrokerHistoryError('MetaTrader 5 symbol discovery failed; previous catalog retained', category='provider') from None
