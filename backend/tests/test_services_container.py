from app.core.config import Settings
from app.services.container import build_services


def test_services_boot_without_external_provider_keys(tmp_path):
    settings = Settings(
        LEDGER_DATA_DIR=tmp_path,
        SEC_USER_AGENT="Ledger/2.0 your-email@example.com",
        ALPACA_API_KEY=None,
        ALPACA_API_SECRET=None,
        FRED_API_KEY=None,
        MASSIVE_API_KEY=None,
        OANDA_ACCESS_TOKEN=None,
    )
    services = build_services(settings)
    try:
        status = services.provider_status()
        assert status["alpaca"]["configured"] is False
        assert status["sec"]["configured"] is False
        assert services.symbol_universe is None
        assert services.market_data is None
    finally:
        services.close()
