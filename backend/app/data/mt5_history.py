"""Broker-native history, separate from verified continuous-futures routing."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from app.brokers.base import BrokerHistoryError
from app.brokers.mt5_symbols import symbol_metadata

FRAMES = {'1m': ('TIMEFRAME_M1', 60), '5m': ('TIMEFRAME_M5', 300),
          '15m': ('TIMEFRAME_M15', 900), '30m': ('TIMEFRAME_M30', 1800),
          '1h': ('TIMEFRAME_H1', 3600), '4h': ('TIMEFRAME_H4', 14400),
          '1d': ('TIMEFRAME_D1', 86400)}
MAX_ROWS = 500000


def history_request(symbol, data_type, start, end):
    if not isinstance(symbol, str) or not symbol or len(symbol) > 256:
        raise BrokerHistoryError('Specify an exact broker symbol', category='configuration')
    if data_type not in {*FRAMES, 'ticks'}:
        raise BrokerHistoryError('Unsupported MT5 history interval', category='configuration')
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None or pd.isna(start) or pd.isna(end):
        raise BrokerHistoryError('History dates must include a timezone', category='configuration')
    start, end = start.tz_convert('UTC'), end.tz_convert('UTC')
    if end <= start or end > pd.Timestamp.now(tz='UTC'):
        raise BrokerHistoryError('Request a completed historical interval', category='configuration')
    if end - start > pd.Timedelta(days=1 if data_type == 'ticks' else 366):
        raise BrokerHistoryError('Request at most one day of ticks or 366 days of bars per window', category='configuration')
    return dict(broker_symbol=symbol, data_type=data_type, requested_start=start.isoformat(),
                requested_end=end.isoformat(), interval_semantics='start_inclusive_end_exclusive',
                timezone='UTC', adjustment_mode='broker_native_unadjusted_by_ledger', schema_version=1)


def read_history(adapter, request):
    """No order APIs; shared terminal lock and verified selected account required."""
    try:
        mt = adapter._module
        symbol, kind = request['broker_symbol'], request['data_type']
        info = mt.symbol_info(symbol)
        if info is None or info.name != symbol:
            raise BrokerHistoryError('Exact broker symbol is unavailable; no alias was substituted', category='history')
        metadata = symbol_metadata(info, mt, adapter.account_key, adapter.environment)
        if not mt.symbol_select(symbol, True):
            raise BrokerHistoryError('Broker symbol cannot be selected', category='history')
        start = pd.Timestamp(request['requested_start']).to_pydatetime()
        end = pd.Timestamp(request['requested_end']).to_pydatetime()
        chunks, count, cursor = [], 0, start
        while cursor < end:
            # Keep native requests bounded; never treat a missing window as coverage.
            stop = min(end, cursor + timedelta(hours=1) if kind == 'ticks' else cursor + timedelta(days=7))
            if kind == 'ticks':
                raw = mt.copy_ticks_range(symbol, cursor, stop, mt.COPY_TICKS_ALL)
            else:
                raw = mt.copy_rates_range(symbol, getattr(mt, FRAMES[kind][0]), cursor, stop)
            if raw is None:
                raise BrokerHistoryError('MT5 history request failed; cached data retained', category='history')
            count += len(raw)
            if count > MAX_ROWS:
                raise BrokerHistoryError('MT5 history exceeds 500000 rows; request a smaller window', category='history')
            frame = pd.DataFrame(raw)
            if not frame.empty:
                time_column, unit = ('time_msc', 'ms') if kind == 'ticks' else ('time', 's')
                frame['timestamp'] = pd.to_datetime(frame[time_column], unit=unit, utc=True, errors='raise')
                frame = frame[(frame.timestamp >= cursor) & (frame.timestamp < stop)].copy()
                chunks.append(frame)
            cursor = stop
        if adapter._account()[1] != adapter.account_key:
            raise BrokerHistoryError('MT5 account changed during history retrieval', category='connection')
        if not chunks:
            raise BrokerHistoryError('No observed MT5 history in the requested interval', category='history')
        frame = pd.concat(chunks, ignore_index=True).sort_values('timestamp', kind='stable')
        if kind == 'ticks':
            columns = ['timestamp', 'bid', 'ask', 'last', 'volume', 'volume_real', 'flags']
            for field in columns[1:]:
                if field not in frame:
                    frame[field] = np.nan
                frame[field] = pd.to_numeric(frame[field], errors='raise')
                if np.isinf(frame[field]).any() or (frame[field].dropna() < 0).any():
                    raise ValueError('Invalid tick field')
            for field in ('bid', 'ask', 'last'):
                frame[field] = frame[field].where(frame[field] > 0)
            if ((frame.ask < frame.bid) & frame.ask.notna() & frame.bid.notna()).any():
                raise ValueError('Crossed quote')
            frame = frame[columns].rename(columns={'volume': 'last_trade_volume', 'volume_real': 'last_trade_volume_real'})
            frame['spread_price'] = frame.ask - frame.bid
            # Do not deduplicate: equal millisecond ticks may be legitimate events.
            frame['event_ordinal'] = range(len(frame))
        else:
            columns = ['timestamp', 'open', 'high', 'low', 'close', 'tick_volume', 'real_volume', 'spread']
            for field in columns[1:]:
                if field not in frame:
                    frame[field] = np.nan
                frame[field] = pd.to_numeric(frame[field], errors='raise')
                if np.isinf(frame[field]).any():
                    raise ValueError('Nonfinite bar field')
            prices = frame[['open', 'high', 'low', 'close']]
            if prices.isna().any().any() or (prices <= 0).any().any():
                raise ValueError('Invalid OHLC')
            if (frame.high < prices.max(axis=1)).any() or (frame.low > prices.min(axis=1)).any():
                raise ValueError('Invalid OHLC range')
            if (frame[['tick_volume', 'real_volume', 'spread']] < 0).any().any():
                raise ValueError('Negative volume/spread')
            frame = frame[columns].rename(columns={'spread': 'spread_points'})
            duplicates = frame[frame.duplicated('timestamp', keep=False)]
            if not duplicates.empty and duplicates.drop_duplicates().timestamp.duplicated().any():
                raise ValueError('Conflicting bars')
            frame = frame.drop_duplicates('timestamp')
            frame = frame[frame.timestamp + pd.Timedelta(seconds=FRAMES[kind][1]) <= end]
        if frame.empty:
            raise BrokerHistoryError('No completed history in this interval', category='history')
        frame = frame.reset_index(drop=True)
        observed = {field: {'non_null_rows': int(frame[field].notna().sum()),
                            'positive_rows': int((frame[field] > 0).sum())}
                    for field in frame if field not in ('timestamp', 'event_ordinal')}
        manifest = {**request, 'provider': 'mt5', 'account_key': adapter.account_key,
                    'environment': adapter.environment, 'instrument_id': metadata['instrument_id'],
                    'instrument_type': metadata['instrument_type'], 'canonical_symbol': None,
                    'symbol_metadata': metadata, 'rows': len(frame),
                    'observed_start': frame.timestamp.min().isoformat(),
                    'observed_end': frame.timestamp.max().isoformat(),
                    'coverage_complete': False, 'coverage_basis': 'observed_records_only_not_contiguous_guarantee',
                    'fields': observed, 'dom': 'unverified',
                    'volume_semantics': 'provider_fields_separate; all-zero real volume does not prove availability',
                    'created_at': datetime.now(timezone.utc).isoformat()}
        return frame, manifest
    except BrokerHistoryError:
        raise
    except Exception:
        raise BrokerHistoryError('Invalid or unavailable MT5 history; cached data retained', category='history') from None
