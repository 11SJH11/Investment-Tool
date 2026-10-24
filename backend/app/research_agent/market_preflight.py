"""No data loading, strategy execution or model calls during market preflight."""
from app.backtesting.strategies.intraday_baselines import KEYS, validate_market


def validate_research_market(key, symbols, timeframe):
    # Reuse the same restriction as BacktestService. This does not broaden ORB rules.
    if key in KEYS:
        for symbol in symbols:
            try:
                validate_market(symbol, timeframe)
            except ValueError:
                raise ValueError('STRATEGY_INSTRUMENT_UNSUPPORTED: ORB/VWAP requires '
                                 'one-minute equities or supported futures with traded volume') from None
