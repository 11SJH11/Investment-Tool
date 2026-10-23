"""One bounded read-only MT5 observation for T01 diagnostics, never execution.

No guessed clock shifts, account login, cached-bar fallback, inferred positions
or historical catch-up. A separate worker may schedule this operation later.
"""
from datetime import datetime, timedelta, timezone
import time

import pandas as pd

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_sizing import finite
from .bars import canonical, stamp


def collect(adapter, *, symbol, expected_start, previous_bar=None, timestamp_policy):
    """Caller holds terminal/profile locks and pins the selected demo identity."""
    from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
    MT5ExecutionLedger._manual_only()
    if timestamp_policy != 'verified_utc':
        raise BrokerHistoryError('T01 feed requires independently verified UTC timestamps', category='configuration')
    try:
        started = time.monotonic()
        now = datetime.fromtimestamp(adapter._clock(), timezone.utc)
        end = now.replace(second=0, microsecond=0)
        expected = stamp(expected_start)
        if expected != end-timedelta(minutes=1):
            raise ValueError('not_latest_completed_minute')
        module = adapter._module
        if getattr(module, 'timestamp_policy', 'verified_utc') != 'verified_utc':
            raise ValueError('bridge_time_unverified')

        def account():
            info, key = adapter._account()
            terminal = module.terminal_info()
            if (adapter.environment != 'demo' or info.trade_mode != module.ACCOUNT_TRADE_MODE_DEMO
                    or key != adapter.account_key or info.currency != adapter.currency
                    or terminal is None or terminal.connected is not True):
                raise ValueError('account_or_connection_changed')
            return finite(info.equity, positive=True)

        def flat():
            positions, orders = module.positions_get(), module.orders_get()
            if positions is None or orders is None or len(positions) or len(orders):
                raise ValueError('position_attribution_required')

        account(); flat()
        info = module.symbol_info(symbol)
        if info is None or info.name != symbol or not module.symbol_select(symbol, True):
            raise ValueError('exact_symbol_unavailable')
        quote = module.symbol_info_tick(symbol)
        quote_received = adapter._clock()*1000
        if quote is None or not 0 <= quote_received-finite(quote.time_msc, positive=True) <= 5000:
            raise ValueError('quote_not_fresh_utc')
        if finite(quote.ask, positive=True) < finite(quote.bid, positive=True):
            raise ValueError('crossed_quote')
        start = expected
        if previous_bar is not None:
            start -= timedelta(minutes=1)
            if stamp(previous_bar['timestamp']) != start:
                raise ValueError('overlap_identity')
        raw = module.copy_rates_range(symbol, module.TIMEFRAME_M1, start, end)
        if raw is None or not 1 <= len(raw) <= 3:
            raise ValueError('minute_history_unavailable')
        values = {}
        for row in pd.DataFrame(raw).to_dict('records'):
            epoch = finite(row['time'], positive=True)
            if epoch != int(epoch):
                raise ValueError('invalid_bar_epoch')
            at = datetime.fromtimestamp(epoch, timezone.utc)
            # Native range retrieval can include the still-forming right edge.
            if at == end:
                continue
            if not start <= at < end or at in values:
                raise ValueError('unexpected_or_duplicate_bar')
            values[at] = canonical(dict(timestamp=at.isoformat(),
                available_at=(at+timedelta(minutes=1)).isoformat(),
                **{key:row[key] for key in ('open','high','low','close')}, volume=row['tick_volume']), now)
        required = {expected} if previous_bar is None else {start, expected}
        if set(values) != required or (previous_bar is not None and values[start] != previous_bar):
            raise ValueError('missing_or_revised_history')
        flat(); equity = account()
        finish = datetime.fromtimestamp(adapter._clock(), timezone.utc)
        if (not 0 <= (finish-now).total_seconds() <= 5 or time.monotonic()-started > 5
                or finish.replace(second=0, microsecond=0) != end
                or not 0 <= finish.timestamp()*1000-quote.time_msc <= 5000):
            raise ValueError('observation_expired')
        return dict(bar=values[expected], observed_at=finish.isoformat(), equity=equity,
            account_key=adapter.account_key, currency=adapter.currency, environment='demo',
            position=None, execution_enabled=False, volume_basis='mt5_tick_volume',
            timestamp_policy='verified_utc', observation_basis='flat_account_before_and_after')
    except Exception:
        raise BrokerHistoryError('T01 observation unavailable: verify demo identity, UTC quote freshness, complete unchanged minutes and a flat account', category='history') from None


def read_minute(connections, profile_id, definition, *, expected_start, previous_bar=None):
    """Use existing locks/adapter, without passing credentials that switch logins."""
    from app.brokers.mt5_execution_ledger import MT5ExecutionLedger
    MT5ExecutionLedger._manual_only()
    if definition.get('timestamp_policy') != 'verified_utc' or definition.get('environment') != 'demo':
        raise BrokerHistoryError('Verified UTC demo definition required', category='configuration')
    profile = connections._profile(profile_id)
    if profile.provider != 'mt5' or profile.environment != 'demo' or not profile.configured:
        raise BrokerHistoryError('An enabled MT5 demo profile is required', category='configuration')
    credentials = {key:profile.credentials.get(key, '') for key in ('terminal_path','bridge_url','bridge_token_file')}
    if not (credentials['terminal_path'] or credentials['bridge_url']):
        raise BrokerHistoryError('Select an explicit demo terminal or bridge; default terminal discovery is disabled', category='configuration')
    lock = connections._profile_locks[profile_id]
    if not lock.acquire(blocking=False):
        raise BrokerHistoryError('MT5 profile is busy', category='busy')
    adapter = None
    try:
        selection_key = connections._selection(profile)
        if connections._setting(selection_key) != definition['account_key']:
            raise BrokerHistoryError('Selected MT5 account differs from T01 definition', category='configuration')
        adapter = connections.factories['mt5'](credentials, 'demo')
        adapter.connect(definition['account_key'])
        if adapter.currency != definition['currency']:
            raise BrokerHistoryError('MT5 account currency changed', category='configuration')
        result = collect(adapter, symbol=definition['symbol'], expected_start=expected_start,
            previous_bar=previous_bar, timestamp_policy=definition['timestamp_policy'])
        if (not profile.configured or profile.environment != 'demo'
                or connections._setting(selection_key) != definition['account_key']):
            raise BrokerHistoryError('MT5 profile changed during observation', category='configuration')
        return result
    except BrokerHistoryError:
        raise
    except Exception:
        raise BrokerHistoryError('T01 feed failed; existing decisions retained', category='connection') from None
    finally:
        try:
            if adapter is not None:
                adapter.close()
        finally:
            lock.release()
