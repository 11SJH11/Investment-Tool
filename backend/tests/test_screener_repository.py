from pathlib import Path

from app.data.providers.base import Symbol
from app.storage.database import Database
from app.storage.screener_repository import ScreenerFilters, ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


def test_screener_filters_and_computed_metrics(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    symbols = SymbolRepository(db)
    symbols.upsert_many([
        Symbol("AAA", "Alpha", exchange="NASDAQ", tradable=True),
        Symbol("BBB", "Beta", exchange="NYSE", tradable=True),
    ], "test")
    repo = ScreenerRepository(db)
    repo.upsert_fundamentals([
        {"ticker":"AAA","cik":"1","company_name":"Alpha","fiscal_year":2025,"period_end":"2025-12-31","revenue":1000,"revenue_growth_yoy":0.20,"net_income":200,"net_margin":0.20,"operating_income":250,"operating_margin":0.25,"assets":2000,"liabilities":500,"equity":1500,"cash":100,"operating_cash_flow":300,"capital_expenditure":50,"free_cash_flow":250,"eps_diluted":5,"shares_outstanding":100,"return_on_equity":0.133,"source":"sec"},
        {"ticker":"BBB","cik":"2","company_name":"Beta","fiscal_year":2025,"period_end":"2025-12-31","revenue":1000,"revenue_growth_yoy":-0.10,"net_income":10,"net_margin":0.01,"operating_income":20,"operating_margin":0.02,"assets":2000,"liabilities":1500,"equity":500,"cash":20,"operating_cash_flow":10,"capital_expenditure":20,"free_cash_flow":-10,"eps_diluted":1,"shares_outstanding":100,"return_on_equity":0.02,"source":"sec"},
    ])
    repo.upsert_snapshots([
        {"ticker":"AAA","price":50,"timestamp":"2026-01-01T00:00:00Z"},
        {"ticker":"BBB","price":10,"timestamp":"2026-01-01T00:00:00Z"},
    ], "test")
    total, rows = repo.screen(ScreenerFilters(min_revenue_growth=0.10, positive_fcf=True, max_pe=15), sort_by="market_cap", sort_dir="desc")
    assert total == 1
    assert rows[0]["ticker"] == "AAA"
    assert rows[0]["market_cap"] == 5000
    assert rows[0]["pe_ratio"] == 10
