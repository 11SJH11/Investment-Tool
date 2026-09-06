from pathlib import Path

from app.data.providers.base import Symbol
from app.services.research import ResearchService
from app.storage.database import Database
from app.storage.screener_repository import ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


class FakeScreener:
    def __init__(self, repo):
        self.repo = repo

    def refresh_one_price(self, ticker):
        self.repo.upsert_snapshots([{"ticker": ticker, "price": 42.0, "timestamp": "2026-08-27T15:00:00Z"}], "fake")
        return {"ticker": ticker, "price": 42.0}


def test_research_returns_price_for_security_without_sec_fundamentals(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    symbols = SymbolRepository(db)
    symbols.upsert_many([Symbol("ETF", "Example ETF", exchange="ARCA", tradable=True)], "test")
    repo = ScreenerRepository(db)
    service = ResearchService(symbols, repo, FakeScreener(repo), None)
    result = service.profile("ETF")
    assert result["symbol"]["ticker"] == "ETF"
    assert result["metrics"]["price"] == 42.0
    assert result["metrics"]["revenue"] is None


class FakeFundamentals:
    def __init__(self):
        self.calls = 0

    def get(self, ticker, refresh=False):
        self.calls += 1
        return {
            "ticker": ticker,
            "cik": "0000000001",
            "company_name": "Alpha Inc.",
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "revenue": 1000.0,
            "revenue_growth_yoy": 0.1,
            "net_income": 100.0,
            "net_margin": 0.1,
            "operating_income": 120.0,
            "operating_margin": 0.12,
            "assets": 2000.0,
            "liabilities": 800.0,
            "equity": 1200.0,
            "cash": 200.0,
            "operating_cash_flow": 180.0,
            "capital_expenditure": 30.0,
            "free_cash_flow": 150.0,
            "eps_diluted": 5.0,
            "shares_outstanding": 100.0,
            "return_on_equity": 0.0833,
            "source": "sec",
        }


def test_research_auto_fetches_missing_fundamentals_even_when_price_row_exists(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    symbols = SymbolRepository(db)
    symbols.upsert_many([
        Symbol("AAA", "Alpha Inc.", exchange="NASDAQ", tradable=True, cik="0000000001")
    ], "test")
    repo = ScreenerRepository(db)
    repo.upsert_snapshot("AAA", 50.0, "2026-08-27T15:00:00Z", "fake")
    fundamentals = FakeFundamentals()
    service = ResearchService(symbols, repo, FakeScreener(repo), fundamentals)

    result = service.profile("AAA")

    assert fundamentals.calls == 1
    assert result["metrics"]["price"] == 50.0
    assert result["metrics"]["revenue"] == 1000.0
    assert result["metrics"]["has_fundamentals"] is True
    assert result["availability"]["fundamentals"]["status"] == "available"
