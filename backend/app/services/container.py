from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.data.http import JsonHttpClient
from app.data.massive_request_gate import MassiveRequestGate
from app.data.providers.alpaca import AlpacaProvider
from app.data.providers.autochartist import AutochartistProvider
from app.data.providers.massive_futures import MassiveFuturesProvider
from app.data.providers.oanda import OandaProvider
from app.data.instruments import InstrumentSpec
from app.data.providers.fred import FredProvider
from app.data.providers.registry import ProviderRegistry
from app.data.providers.sec import SecProvider
from app.services.fundamentals import FundamentalsService
from app.services.backtest import BacktestService
from app.services.backtest_jobs import BacktestJobs
from app.services.macro import MacroService
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService
from app.services.execution_price import ExecutionPriceService
from app.services.fx import FxRateService
from app.services.journal import JournalService
from app.services.broker_sync import BrokerSyncService
from app.services.broker_connections import BrokerConnections
from app.services.broker_scheduler import BrokerScheduler
from app.services.research import ResearchService
from app.services.screener import ScreenerService
from app.services.symbols import SymbolUniverseService
from app.storage.database import Database
from app.storage.json_cache import JsonCacheRepository
from app.storage.market_cache_repository import MarketCacheRepository
from app.storage.market_store import MarketStore
from app.storage.research_repository import ResearchRepository
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
    autochartist: AutochartistProvider
    screener_repository: ScreenerRepository
    screener: ScreenerService
    research: ResearchService
    portfolio: PortfolioService
    journal: JournalService
    journal_repository: JournalRepository
    backtest: BacktestService
    backtest_runs: BacktestRunRepository
    http: JsonHttpClient
    broker_sync: BrokerSyncService
    broker_connections: BrokerConnections
    backtest_jobs: BacktestJobs | None = None
    broker_scheduler: BrokerScheduler | None = None

    def close(self) -> None:
        if self.broker_scheduler:
            self.broker_scheduler.close()
        if self.backtest_jobs:
            self.backtest_jobs.close()
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
            "massive": {
                "configured": self.settings.massive_configured,
                "purpose": "CME/CBOT/NYMEX/COMEX futures bars and contract reference data",
                "continuous_roll": "prior-session-volume45-v1",
                "reference_discovery": "dated single-contract snapshots",
                "calls_per_minute": self.settings.massive_calls_per_minute,
                "back_adjust": self.settings.futures_back_adjust,
            },
            "oanda": {
                "configured": self.settings.oanda_configured,
                "purpose": "OANDA spot/CFD-style market data (Phase 6.2: XAUUSD)",
                "environment": self.settings.oanda_environment,
                "account_id_required_for_candles": False,
                "journal_configured": self.settings.oanda_journal_configured,
                "journal_read_only": True,
            },
            "autochartist": {
                "configured": self.autochartist.configured,
                "purpose": "Future normalised Autochartist research feed; scaffold only until approved API credentials are available",
                "status": self.autochartist.capability_report()["status"],
                "remote_probe_performed": False,
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

    autochartist = AutochartistProvider(
        enabled=settings.autochartist_enabled,
        broker_id=settings.autochartist_broker_id,
        user=settings.autochartist_user,
        account_type=settings.autochartist_account_type,
        secret_key=settings.autochartist_secret_key,
    )

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

    massive_provider: MassiveFuturesProvider | None = None
    if settings.massive_configured:
        massive_provider = MassiveFuturesProvider(
            settings.massive_api_key or "",
            base_url=settings.massive_futures_base_url,
            back_adjust=settings.futures_back_adjust,
            reference_cache_path=settings.market_data_dir / "contract-reference.sqlite",
            http=MassiveRequestGate(http, settings.massive_api_key, calls_per_minute=settings.massive_calls_per_minute),
        )
        providers.register("market_data_futures", massive_provider)

    oanda_provider: OandaProvider | None = None
    if settings.oanda_configured:
        oanda_provider = OandaProvider(
            settings.oanda_access_token or "",
            environment=settings.oanda_environment,
            practice_base_url=settings.oanda_practice_base_url,
            live_base_url=settings.oanda_live_base_url,
            http=http,
        )
        providers.register("market_data_oanda", oanda_provider)

    macro_service: MacroService | None = None
    fred_provider: FredProvider | None = None
    if settings.fred_configured:
        fred_provider = FredProvider(settings.fred_api_key or "", base_url=settings.fred_base_url, http=http)
        providers.register("macro", fred_provider)
        macro_service = MacroService(fred_provider, json_cache, ttl_seconds=settings.macro_cache_minutes * 60)

    configured = set(providers.configured())
    security_master = providers.get("security_master") if "security_master" in configured else None
    symbol_universe = SymbolUniverseService(symbols, security_master, sec_provider) if security_master is not None else None
    market_providers = {
        "alpaca": alpaca_provider,
        "massive": massive_provider,
        "oanda": oanda_provider,
    }

    def resolve_market_provider(symbol: str, spec: InstrumentSpec):
        provider = market_providers.get(spec.provider_key)
        if provider is None:
            if spec.provider_key == "oanda":
                raise RuntimeError("OANDA market data is not configured; set OANDA_ACCESS_TOKEN in backend/.env")
            if spec.provider_key == "massive":
                raise RuntimeError("Massive Futures is not configured; set MASSIVE_API_KEY in backend/.env")
            raise RuntimeError("Alpaca market data is not configured; set ALPACA_API_KEY and ALPACA_API_SECRET in backend/.env")
        return provider

    default_market_provider = alpaca_provider or oanda_provider or massive_provider
    market_data = (
        MarketDataService(default_market_provider, market_store, coverage, provider_resolver=resolve_market_provider)
        if default_market_provider is not None else None
    )

    screener = ScreenerService(screener_repository, symbols, alpaca=alpaca_provider, sec=sec_provider)
    research_repository = ResearchRepository(database)
    research = ResearchService(symbols, screener_repository, screener, fundamentals_service, research_repository)
    portfolio_repository = PortfolioRepository(database)
    journal_repository = JournalRepository(database)
    portfolio = PortfolioService(
        portfolio_repository, screener_repository, screener,
        ExecutionPriceService(market_data), FxRateService(fred_provider),
    )
    journal = JournalService(journal_repository)
    backtest_runs = BacktestRunRepository(database)
    backtest = BacktestService(market_data, backtest_runs)

    broker_sync = BrokerSyncService(settings, database)
    broker_connections = BrokerConnections(settings, database, legacy_oanda=broker_sync)
    return AppServices(
        settings=settings, database=database, providers=providers, symbols=symbols,
        symbol_universe=symbol_universe, market_data=market_data,
        fundamentals=fundamentals_service, macro=macro_service, autochartist=autochartist,
        screener_repository=screener_repository, screener=screener,
        research=research, portfolio=portfolio, journal=journal, journal_repository=journal_repository, backtest=backtest, backtest_runs=backtest_runs, http=http,
        broker_sync=broker_sync,
        broker_connections=broker_connections,
        broker_scheduler=BrokerScheduler(broker_connections, database),
        backtest_jobs=BacktestJobs(database, backtest, settings.max_concurrent_backtests),
    )
