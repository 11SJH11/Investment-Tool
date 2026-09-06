from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.data.http import JsonHttpClient
from app.data.providers.alpaca import AlpacaProvider
from app.data.providers.fred import FredProvider
from app.data.providers.registry import ProviderRegistry
from app.data.providers.sec import SecProvider
from app.services.fundamentals import FundamentalsService
from app.services.backtest import BacktestService
from app.services.macro import MacroService
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService
from app.services.execution_price import ExecutionPriceService
from app.services.fx import FxRateService
from app.services.journal import JournalService
from app.services.research import ResearchService
from app.services.screener import ScreenerService
from app.services.symbols import SymbolUniverseService
from app.storage.database import Database
from app.storage.json_cache import JsonCacheRepository
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore
from app.storage.portfolio_repository import PortfolioRepository
from app.storage.journal_repository import JournalRepository
from app.storage.screener_repository import ScreenerRepository
from app.storage.symbol_repository import SymbolRepository
from app.storage.backtest_run_repository import BacktestRunRepository


@dataclass
class AppServices:
    settings: Settings
    database: Database
    providers: ProviderRegistry
    symbols: SymbolRepository
    symbol_universe: SymbolUniverseService | None
    market_data: MarketDataService | None
    fundamentals: FundamentalsService | None
    macro: MacroService | None
    screener_repository: ScreenerRepository
    screener: ScreenerService
    research: ResearchService
    portfolio: PortfolioService
    journal: JournalService
    journal_repository: JournalRepository
    backtest: BacktestService
    backtest_runs: BacktestRunRepository
    http: JsonHttpClient

    def close(self) -> None:
        self.http.close()

    def provider_status(self) -> dict:
        return {
            "alpaca": {
                "configured": self.settings.alpaca_configured,
                "purpose": "US symbol universe and OHLCV market data",
                "historical_feed": self.settings.alpaca_historical_feed,
                "live_feed": self.settings.alpaca_live_feed,
                "historical_delay_minutes": self.settings.alpaca_historical_delay_minutes,
                "adjustment": self.settings.alpaca_adjustment,
            },
            "sec": {
                "configured": self.settings.sec_configured,
                "purpose": "US company filing fundamentals",
                "cache_hours": self.settings.fundamentals_cache_hours,
            },
            "fred": {
                "configured": self.settings.fred_configured,
                "purpose": "Macro-economic series",
                "cache_minutes": self.settings.macro_cache_minutes,
            },
        }


def build_services(settings: Settings) -> AppServices:
    database = Database(settings.database_path)
    database.initialize()
    symbols = SymbolRepository(database)
    screener_repository = ScreenerRepository(database)
    market_store = MarketStore(settings.market_data_dir)
    coverage = MarketCacheRepository(database)
    json_cache = JsonCacheRepository(database)
    providers = ProviderRegistry()
    http = JsonHttpClient(timeout_seconds=settings.http_timeout_seconds)

    sec_provider: SecProvider | None = None
    fundamentals_service: FundamentalsService | None = None
    if settings.sec_configured:
        sec_provider = SecProvider(
            settings.sec_user_agent or "", data_base_url=settings.sec_data_base_url,
            files_base_url=settings.sec_files_base_url, http=http,
        )
        providers.register("fundamentals", sec_provider)
        fundamentals_service = FundamentalsService(
            sec_provider, json_cache, ttl_seconds=settings.fundamentals_cache_hours * 3600,
        )

    alpaca_provider: AlpacaProvider | None = None
    if settings.alpaca_configured:
        alpaca_provider = AlpacaProvider(
            settings.alpaca_api_key or "", settings.alpaca_api_secret or "",
            historical_feed=settings.alpaca_historical_feed,
            live_feed=settings.alpaca_live_feed,
            adjustment=settings.alpaca_adjustment,
            historical_delay_minutes=settings.alpaca_historical_delay_minutes,
            trading_base_url=settings.alpaca_trading_base_url,
            data_base_url=settings.alpaca_data_base_url, http=http,
        )
        providers.register("security_master", alpaca_provider)
        providers.register("market_data", alpaca_provider)
    elif sec_provider is not None:
        providers.register("security_master", sec_provider)

    macro_service: MacroService | None = None
    fred_provider: FredProvider | None = None
    if settings.fred_configured:
        fred_provider = FredProvider(settings.fred_api_key or "", base_url=settings.fred_base_url, http=http)
        providers.register("macro", fred_provider)
        macro_service = MacroService(fred_provider, json_cache, ttl_seconds=settings.macro_cache_minutes * 60)

    configured = set(providers.configured())
    security_master = providers.get("security_master") if "security_master" in configured else None
    symbol_universe = SymbolUniverseService(symbols, security_master, sec_provider) if security_master is not None else None
    market_data = MarketDataService(alpaca_provider, market_store, coverage) if alpaca_provider is not None else None

    screener = ScreenerService(screener_repository, symbols, alpaca=alpaca_provider, sec=sec_provider)
    research = ResearchService(symbols, screener_repository, screener, fundamentals_service)
    portfolio_repository = PortfolioRepository(database)
    journal_repository = JournalRepository(database)
    portfolio = PortfolioService(
        portfolio_repository, screener_repository, screener,
        ExecutionPriceService(market_data), FxRateService(fred_provider),
    )
    journal = JournalService(journal_repository)
    backtest_runs = BacktestRunRepository(database)
    backtest = BacktestService(market_data, backtest_runs)

    return AppServices(
        settings=settings, database=database, providers=providers, symbols=symbols,
        symbol_universe=symbol_universe, market_data=market_data,
        fundamentals=fundamentals_service, macro=macro_service,
        screener_repository=screener_repository, screener=screener,
        research=research, portfolio=portfolio, journal=journal, journal_repository=journal_repository, backtest=backtest, backtest_runs=backtest_runs, http=http,
    )
