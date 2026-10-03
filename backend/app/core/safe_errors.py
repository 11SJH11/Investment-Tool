"""Allowlisted user messages; never include exception text, URLs or provider bodies."""
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime, timedelta, timezone
import math
import sqlite3
from app.data.http import ProviderHttpError

class MissingHistoryError(RuntimeError):
    pass

class MissingHistoryParameterError(ValueError):
    pass

class ProviderConfigurationError(ValueError):
    pass

class ProviderUnavailableError(RuntimeError):
    pass

_MESSAGES = {
    'authentication': 'Provider authentication/configuration failed. Check credentials in Settings.',
    'entitlement': 'Provider denied access (HTTP 403). Check account permissions and history entitlement.',
    'missing_history': 'No usable history or dated contracts were returned for this range. Check symbol, dates and provider coverage.',
    'invalid_parameters': 'Invalid strategy or request parameters. Check the selected strategy, dates and parameter values.',
    'indicator_execution': 'Indicator calculation failed. Check the indicator configuration and available history.',
    'strategy_execution': 'Strategy execution failed. Check the exact configuration with a small deterministic test before retrying.',
    'storage': 'Storage/cache operation failed. Check disk space and filesystem/database access before retrying.',
    'worker_termination': 'A simulation worker stopped unexpectedly. Check memory availability, reduce workers and retry incomplete work.',
    'provider': 'Provider request failed. Check provider availability; retry when service is restored.',
    'unknown': 'Operation failed for an unclassified reason. Check configuration and service availability before retrying.',
}

def safe_failure(exc, *, default='unknown', now=None):
    from app.storage.market_store import MarketCacheCorruption
    category=default if default in _MESSAGES else 'unknown'
    code=exc.status_code if isinstance(exc,ProviderHttpError) else None
    if code==429:
        try: delay=float(exc.retry_after)
        except (TypeError,ValueError,OverflowError): delay=60.
        if not math.isfinite(delay) or delay<=0: delay=60.
        # Datetime-safe cap; ordinary provider cooldowns are preserved exactly.
        delay=min(delay,31536000.)
        retry=((now or datetime.now(timezone.utc))+timedelta(seconds=delay)).isoformat()
        return 'rate_limited',f'Provider rate limited (HTTP 429). Retry no earlier than {retry}.',retry
    if code==401 or isinstance(exc,(ProviderConfigurationError,ProviderUnavailableError)): category='authentication'
    elif code==403: category='entitlement'
    elif isinstance(exc,(MissingHistoryError,MissingHistoryParameterError)): category='missing_history'
    elif isinstance(exc,BrokenProcessPool): category='worker_termination'
    elif isinstance(exc,(ConnectionError,TimeoutError,ProviderHttpError)): category='provider'
    elif isinstance(exc,(OSError,sqlite3.Error,MarketCacheCorruption)): category='storage'
    elif isinstance(exc,(ValueError,TypeError)) and default!='strategy_execution': category='invalid_parameters'
    return category,_MESSAGES[category],None
