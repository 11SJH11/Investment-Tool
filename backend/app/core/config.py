from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ledger"
    environment: str = Field(default="development", validation_alias="LEDGER_ENV")
    api_prefix: str = Field(default="/api", validation_alias="LEDGER_API_PREFIX")
    data_dir: Path = Field(default=Path("./data"), validation_alias="LEDGER_DATA_DIR")
    http_timeout_seconds: float = Field(default=30.0, validation_alias="LEDGER_HTTP_TIMEOUT_SECONDS")

    # Alpaca: security master + market data. Free Basic uses delayed SIP history and IEX live data.
    alpaca_api_key: str | None = Field(default=None, validation_alias="ALPACA_API_KEY")
    alpaca_api_secret: str | None = Field(default=None, validation_alias="ALPACA_API_SECRET")
    alpaca_historical_feed: str = Field(default="sip", validation_alias="ALPACA_HISTORICAL_FEED")
    alpaca_live_feed: str = Field(default="iex", validation_alias="ALPACA_LIVE_FEED")
    alpaca_adjustment: str = Field(default="split", validation_alias="ALPACA_ADJUSTMENT")
    alpaca_historical_delay_minutes: int = Field(default=15, validation_alias="ALPACA_HISTORICAL_DELAY_MINUTES")
    alpaca_trading_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias="ALPACA_TRADING_BASE_URL",
    )
    alpaca_data_base_url: str = Field(
        default="https://data.alpaca.markets",
        validation_alias="ALPACA_DATA_BASE_URL",
    )

    # Futures / metals providers. Phase 6.1.2 records configuration now; provider
    # routing is intentionally added in the dedicated futures phase rather than
    # pretending Alpaca equity bars can represent CME/COMEX instruments.
    futures_data_provider: str = Field(default="massive", validation_alias="FUTURES_DATA_PROVIDER")
    massive_api_key: str | None = Field(default=None, validation_alias="MASSIVE_API_KEY")
    massive_futures_base_url: str = Field(default="https://api.massive.com", validation_alias="MASSIVE_FUTURES_BASE_URL")
    futures_back_adjust: bool = Field(default=False, validation_alias="FUTURES_BACK_ADJUST")
    oanda_access_token: str | None = Field(default=None, validation_alias="OANDA_ACCESS_TOKEN")
    oanda_account_id: str | None = Field(default=None, validation_alias="OANDA_ACCOUNT_ID")
    oanda_environment: str = Field(default="practice", validation_alias="OANDA_ENVIRONMENT")
    oanda_practice_base_url: str = Field(default="https://api-fxpractice.oanda.com", validation_alias="OANDA_PRACTICE_BASE_URL")
    oanda_live_base_url: str = Field(default="https://api-fxtrade.oanda.com", validation_alias="OANDA_LIVE_BASE_URL")


    # Autochartist research integration scaffold. OANDA portal entitlement does
    # not imply developer API credentials, so Ledger never scrapes the portal or
    # guesses authentication. These fields are dormant until explicit credentials
    # and an approved API contract are available.
    autochartist_enabled: bool = Field(default=False, validation_alias="AUTOCHARTIST_ENABLED")
    autochartist_broker_id: str | None = Field(default=None, validation_alias="AUTOCHARTIST_BROKER_ID")
    autochartist_user: str | None = Field(default=None, validation_alias="AUTOCHARTIST_USER")
    autochartist_account_type: str = Field(default="LIVE", validation_alias="AUTOCHARTIST_ACCOUNT_TYPE")
    autochartist_secret_key: str | None = Field(default=None, validation_alias="AUTOCHARTIST_SECRET_KEY")

    # SEC EDGAR APIs do not need a key, but the SEC requires a declared User-Agent.
    sec_user_agent: str | None = Field(default=None, validation_alias="SEC_USER_AGENT")
    sec_data_base_url: str = Field(default="https://data.sec.gov", validation_alias="SEC_DATA_BASE_URL")
    sec_files_base_url: str = Field(default="https://www.sec.gov", validation_alias="SEC_FILES_BASE_URL")

    # FRED macro data.
    fred_api_key: str | None = Field(default=None, validation_alias="FRED_API_KEY")
    fundamentals_cache_hours: int = Field(default=12, validation_alias="FUNDAMENTALS_CACHE_HOURS")
    macro_cache_minutes: int = Field(default=15, validation_alias="MACRO_CACHE_MINUTES")

    fred_base_url: str = Field(
        default="https://api.stlouisfed.org",
        validation_alias="FRED_BASE_URL",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "ledger.db"

    @property
    def market_data_dir(self) -> Path:
        return self.data_dir / "market"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_api_secret)

    @property
    def massive_configured(self) -> bool:
        return bool(self.massive_api_key)

    @property
    def oanda_configured(self) -> bool:
        return bool(self.oanda_access_token)

    @property
    def oanda_journal_configured(self) -> bool:
        return bool((self.oanda_access_token or "").strip() and (self.oanda_account_id or "").strip() and self.oanda_environment.strip().lower() in {"practice", "live"})

    @property
    def autochartist_configured(self) -> bool:
        return bool(
            self.autochartist_enabled
            and self.autochartist_broker_id
            and self.autochartist_user
            and self.autochartist_secret_key
        )

    @property
    def sec_configured(self) -> bool:
        return bool(self.sec_user_agent and "your-email@example.com" not in self.sec_user_agent)

    @property
    def fred_configured(self) -> bool:
        return bool(self.fred_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
