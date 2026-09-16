from pathlib import Path
import sys
import os
import tempfile


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# App imports create upload storage and lifespan initializes SQLite. Never let
# endpoint tests use a developer's real data directory or provider credentials.
_test_data = tempfile.TemporaryDirectory(prefix="ledger-test-app-", ignore_cleanup_errors=True)
os.environ["LEDGER_DATA_DIR"] = _test_data.name
for _credential in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "OANDA_ACCESS_TOKEN", "OANDA_ACCOUNT_ID", "MASSIVE_API_KEY", "FRED_API_KEY", "SEC_USER_AGENT", "TRADING212_API_KEY", "TRADING212_API_SECRET", "TRADOVATE_CLIENT_ID", "TRADOVATE_CLIENT_SECRET", "TRADOVATE_ACCOUNT_ID"):
    os.environ[_credential] = ""
os.environ['BROKER_PROFILES_JSON'] = '[]'
os.environ['TRADING212_ENABLED'] = 'false'
os.environ['TRADOVATE_ENABLED'] = 'false'
