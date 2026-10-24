"""Performance-blind queue selection and timestamp-only local coverage discovery.

This adapter never downloads bars or reads OHLCV columns. Observed session dates
are not an exchange-calendar completeness claim. Missing cache blocks planning.
"""
from datetime import timedelta
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from app.backtesting.strategies import strategy_registry
from app.data.instruments import instrument_spec
from .analysis import digest
from .campaigns import Campaigns, utcnow
from .dataset_planner import SessionCoverage


# Explicit research catalog, not a profitability ranking or a stock universe.
FAMILIES = (
    ('vwap_continuation', 'vwap_trend_confirmation_quality_research_v5'),
    ('opening_range', 'opening_range_breakout_research_v1'),
    ('vwap_reversion', 'vwap_mean_reversion_research_v1_reattached'),
    ('donchian', 'turtle_donchian_research_v1'),
)
MAX_COVERAGE_ROWS = 2_000_000


def required_timeframes(entries, primary):
    from app.backtesting.strategies.intraday_baselines import ORB_DIAGNOSTIC_KEYS
    from app.market_concepts import registry as concepts
    specs = {s.key: s for s in strategy_registry.specs()}
    result = list(primary)
    for entry in entries:
        spec = specs[entry['strategy_key']]
        # BacktestService explicitly treats ORB daily diagnostics as optional.
        frames = [tf for tf in spec.timeframes if not (tf == '1d' and spec.key in ORB_DIAGNOSTIC_KEYS)]
        frames += [d['timeframe'] for d in concepts.declarations(spec.concepts).values()]
        result.extend(frames)
    return list(dict.fromkeys(result))


def campaign_coverage(market_data, policy, entries, **bounds):
    """Freeze dependencies without making independent projects or moving splits."""
    output = []
    required = required_timeframes(entries, policy['timeframes'])
    for symbol in policy['symbols']:
        inputs = {tf: cached_coverage(market_data, symbol, tf, **bounds) for tf in required}
        for primary in policy['timeframes']:
            coverage = inputs[primary]
            for tf, dependency in inputs.items():
                if dependency.provider_namespace != coverage.provider_namespace:
                    raise ValueError('Required timeframes use different providers')
                if not set(coverage.sessions) <= set(dependency.sessions):
                    raise ValueError(f'Required {tf} history is missing primary session dates; prepare complete history')
            output.append(coverage.model_copy(update={
                'input_namespaces': {tf: d.provider_namespace for tf, d in inputs.items()},
                'input_fingerprints': {tf: d.source_fingerprint for tf, d in inputs.items()},
            }).model_dump(mode='json'))
    return output


def queue(request):
    specs = {s.key: s for s in strategy_registry.specs()}
    policy = request['policy']
    if request['mode'] == 'RESEARCH_IDEA':
        raise ValueError('Novel idea synthesis needs the Code Author; no unrelated strategy is substituted')
    if request['mode'] == 'IMPROVE_STRATEGY':
        choices = [('selected_strategy', request['strategy_key'])]
    else:
        choices = FAMILIES
    selected = []
    for family, key in choices:
        spec = specs.get(key)
        # timeframes lists required inputs, not interchangeable primary bars.
        if not spec or any(tf != spec.timeframes[0] for tf in policy['timeframes']):
            continue
        from .market_preflight import validate_research_market
        validate_research_market(key, policy['symbols'], spec.timeframes[0])
        selected.append(dict(family_id=family, strategy_key=key,
                             reason='Registered research family; deterministic catalog order, no performance selection'))
    if not selected:
        raise ValueError('No catalog strategy matches the requested primary timeframe')
    return selected[:policy['budget']['families']]


def cached_coverage(market_data, symbol, timeframe, *, now=None, start=None, end=None):
    now = now or utcnow()
    if now.utcoffset() is None:
        raise ValueError('Coverage clock must be timezone aware')
    if instrument_spec(symbol).session_profile not in {'us_equity', 'oanda_24h'}:
        raise ValueError('Automatic discovery requires supported equity or spot-metal identity')
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,79}', symbol):
        raise ValueError('Unsupported cache symbol')
    if timeframe not in {'1m', '5m', '15m', '30m', '1h', '4h', '1d'}:
        raise ValueError('Unsupported cache timeframe')
    provider = market_data.provider_for(symbol)
    namespace = provider.cache_namespace
    path = market_data.store._path(namespace, symbol, timeframe).resolve()
    root = Path(market_data.store.root).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Historical cache unavailable; load market history before automatic preparation')
    before = path.stat()
    try:
        with duckdb.connect() as connection:
            # Projection is intentional: no prices, volume, results or source SQL.
            clauses=[]
            params=[str(path)]
            for bound, operator in ((start, '>='), (end, '<')):
                if bound is not None:
                    value=pd.Timestamp(bound)
                    if value.tzinfo is None: raise ValueError('Coverage bounds need a timezone')
                    clauses.append('timestamp '+operator+' ?')
                    params.append(value.to_pydatetime())
            where=' WHERE '+' AND '.join(clauses) if clauses else ''
            frame = connection.execute('SELECT timestamp FROM read_parquet(?)'+where+' ORDER BY timestamp LIMIT ?',
                                       [*params, MAX_COVERAGE_ROWS + 1]).df()
    except Exception:
        raise ValueError('Cached timestamp coverage is unreadable') from None
    after = path.stat()
    if len(frame) > MAX_COVERAGE_ROWS:
        raise ValueError('Cached history exceeds the bounded automatic discovery limit')
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('History changed during discovery; retry preparation')
    timestamps = pd.to_datetime(frame['timestamp'], utc=True, errors='coerce')
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ValueError('Cached timestamps contain invalid or duplicate rows')
    local = timestamps.dt.tz_convert('America/New_York')
    # Completed prior NY dates only; also exclude current UTC date for planner.
    cutoff = min(now.date(), now.astimezone(ZoneInfo('America/New_York')).date())
    sessions = sorted(set(local.dt.date[local.dt.date < cutoff]))
    if not sessions:
        raise ValueError('No completed cached session dates')
    return SessionCoverage(symbol=symbol, timeframe=timeframe, provider_namespace=namespace,
                           completed_through=cutoff-timedelta(days=1), sessions=sessions,
                           source_fingerprint=digest(dict(version='cached_timestamps_v1', namespace=namespace,
                                                          symbol=symbol, timeframe=timeframe,
                                                          timestamps=[t.isoformat() for t in timestamps[local.dt.date < cutoff]])))


def prepare(services, identifier):
    campaigns = Campaigns(services.database)
    item = campaigns.get(identifier)
    if item['status'] != 'DRAFT':
        if item.get('discovery', {}).get('version') == 'cached_discovery_v1':
            return item
        raise ValueError('Campaign already prepared through another workflow')
    if services.market_data is None:
        raise ValueError('Market-data service unavailable')
    policy = item['request']['policy']
    entries = queue(item['request'])
    coverages = campaign_coverage(services.market_data, policy, entries)
    discovery = dict(version='cached_discovery_v1', provider_calls=0,
            price_columns_read=False, warnings=[
                'Observed cached dates are not a certified exchange calendar; missing sessions/intraday gaps are not inferred.',
                'No point-in-time stock universe is used. Historical universe may contain survivorship bias.',
                'Novel ideas and unavailable history require additional preparation; no fabricated data.'])
    return campaigns.prepare(identifier, entries, coverages, discovery=discovery)
