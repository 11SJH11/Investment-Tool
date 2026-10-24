"""Actionable preparation failures without echoing provider exception content."""
from app.core.safe_errors import safe_failure


def preparation_failure(exc):
    text = str(exc)
    messages = (
        ('STRATEGY_INSTRUMENT_UNSUPPORTED:', 'strategy_instrument_unsupported', 'The selected ORB/VWAP strategy requires one-minute equities or supported futures with traded volume. Select compatible research; no substitute or simulation was dispatched.'),
        ('Historical cache unavailable', 'required_history_missing', 'Required historical input is not cached. Use provider preparation to load all strategy timeframes.'),
        ('Required ', 'required_history_incomplete', 'A required strategy timeframe is incomplete or uses a different provider. Prepare matching history; dataset dates were not moved.'),
        ('Insufficient completed history', 'insufficient_history', 'There are not enough completed sessions for the declared warmup, development and holdout. Load more history or explicitly revise the dataset policy.'),
        ('No catalog strategy matches', 'strategy_timeframe_mismatch', 'Select the strategy primary execution timeframe. Additional signal timeframes are prepared automatically.'),
        ('Provider namespace changed', 'provider_changed', 'The provider changed after preparation authorization. Create a separate campaign with a fixed source.'),
        ('Market-data service unavailable', 'market_data_unavailable', 'Market data is unavailable. Configure a supported provider before preparing this campaign.'),
    )
    for prefix,category,message in messages:
        if text.startswith(prefix):return {'category':category,'message':message}
    category,message,_=safe_failure(exc)
    return {'category':category,'message':message}
