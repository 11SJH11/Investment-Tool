"""Read-only futures checks. No exchange/broker margin assumptions."""
from datetime import datetime, time, timedelta
from math import floor
from zoneinfo import ZoneInfo
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.intraday_baselines import KEYS, validate_market
from app.data.futures import execution_contract, execution_economics, validate_execution_frame, validate_execution_symbol
from app.data.instruments import instrument_spec


def preflight(service, payload):
    symbols = payload.get('symbols', [])
    symbols = symbols.replace(',', ' ').split() if isinstance(symbols, str) else symbols
    if len(symbols) != 1:
        raise ValueError('Requires one futures symbol')
    symbol = symbols[0].upper()
    spec = instrument_spec(symbol)
    if spec.asset_type != 'future':
        raise ValueError('Requires a futures symbol')
    validate_execution_symbol(symbol)
    strategy = strategy_registry.create(payload['strategy_key'], **payload.get('strategy_params', {}))
    tf, session = payload.get('primary_timeframe', '1m'), payload.get('session', '24h')
    from app.services.backtest import SUPPORTED_TIMEFRAMES, GOLD_EXPERIMENT_KEYS, MOMENTUM_KEY
    if tf not in SUPPORTED_TIMEFRAMES or strategy.spec.key in GOLD_EXPERIMENT_KEYS or strategy.spec.key == MOMENTUM_KEY:
        raise ValueError('Strategy/timeframe does not support futures')
    if session=='auto':session='24h'
    if strategy.spec.key in KEYS:
        validate_market(symbol, tf)
    if session not in ('regular', 'extended', '24h'):
        raise ValueError('Unsupported session')
    report = dict(symbol=symbol, recognised=True, provider=getattr(service._provider(symbol), 'key', None),
                  requested_period=[payload['start_date'], payload['end_date']], execution_mode='raw dated contracts',
                  strategy=strategy.spec.key, timeframe=tf, session=session,
                  strategy_window='09:30–16:00 America/New_York' if strategy.spec.key in KEYS else 'Strategy-defined',
                  ready=False, warnings=[], limitations=['Preflight is not a simulation. Signal stops and subsequent equity determine actual sizing. No CME/broker margin is assumed.'])
    start = datetime.combine(datetime.fromisoformat(payload['start_date']).date(), time.min, ZoneInfo('America/New_York'))
    end = datetime.combine(datetime.fromisoformat(payload['end_date']).date()+timedelta(days=1), time.min, ZoneInfo('America/New_York'))
    if start >= end:
        raise ValueError('Invalid requested period')
    try:
        frame = service._load_timeframe(symbol, tf, start, end, session)
    except Exception:
        report['reason'] = 'Raw execution data unavailable. Check provider entitlement, coverage and cooldown; no simulation was started.'
        return report
    if frame.empty:
        report['reason'] = 'No execution bars available for this period'
        return report
    if spec.security_type == 'continuous_future' and ('source_contract' not in frame or frame.source_contract.isna().any()):
        report['reason'] = 'Continuous source provenance unavailable'
        return report
    try:
        validate_execution_frame(symbol, frame)
        source = execution_contract(symbol, frame.iloc[0])
    except ValueError:
        report['reason'] = 'Execution provenance invalid: raw, unadjusted dated contracts from the correct family are required'
        return report
    multiplier, tick, step = execution_economics(source)
    price = float(frame.iloc[0].open)
    notional = price * multiplier
    capital = float(payload.get('starting_balance', 10000)) * float(payload.get('max_leverage', 1))
    capacity = max(0, floor(capital / notional)) if notional > 0 else 0
    report.update(bars=len(frame), first_bar=str(frame.iloc[0].timestamp), last_bar=str(frame.iloc[-1].timestamp),
                  source_contracts=sorted(set(frame.source_contract)) if 'source_contract' in frame else [source],
                  schedule_versions=sorted(set(frame.roll_schedule_version)) if 'roll_schedule_version' in frame else ['dated'],
                  provenance_available=True, tick_size=tick, point_value=multiplier, tick_value=tick*multiplier,
                  quantity_step=step, reference_open=price, reference_full_notional=notional,
                  starting_full_notional_capacity=capacity)
    mode, value = payload.get('sizing_mode', 'risk_pct'), float(payload.get('risk_value', 1))
    known = {'quantity': value, 'cash_position': value/notional,
             'position_pct': float(payload.get('starting_balance', 10000))*value/100/notional}.get(mode)
    if capacity < 1 or (known is not None and floor(known) < 1):
        report['reason'] = 'Position sizing rounds to zero at the reference open under current full-notional leverage settings'
        return report
    if mode in ('risk_pct', 'cash_risk'):
        report['warnings'].append('Risk sizing needs each signal’s stop distance; notional capacity does not guarantee a whole contract.')
    report['ready'] = True
    return report
