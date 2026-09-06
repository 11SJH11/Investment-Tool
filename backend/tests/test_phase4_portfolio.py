from pathlib import Path

import pytest

from app.storage.database import Database
from app.storage.portfolio_repository import PortfolioRepository
from app.storage.screener_repository import ScreenerRepository
from app.services.portfolio import PortfolioService


class FakeScreener:
    def refresh_one_price(self, ticker):
        return {"ticker": ticker, "price": 123.0}


def build(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    with db.connect() as c:
        c.execute("INSERT INTO securities(ticker,name,provider) VALUES ('AAPL','Apple','test')")
    return db, PortfolioService(PortfolioRepository(db), ScreenerRepository(db), FakeScreener())


def test_portfolio_derives_holdings_and_realised_pnl(tmp_path):
    db, service = build(tmp_path)
    service.add_transaction({"account":"Main","ticker":"AAPL","action":"BUY","occurred_at":"2026-01-01T10:00:00Z","quantity":10,"price":100,"fees":0})
    service.add_transaction({"account":"Main","ticker":"AAPL","action":"SELL","occurred_at":"2026-02-01T10:00:00Z","quantity":4,"price":120,"fees":0})
    with db.connect() as c:
        c.execute("INSERT INTO market_snapshots(ticker,price,timestamp,source) VALUES ('AAPL',130,'2026-02-02T10:00:00Z','test')")
    summary = service.summary("Main")
    holding = summary["holdings"][0]
    assert holding["quantity"] == 6
    assert holding["average_cost"] == pytest.approx(100)
    assert holding["cost_basis"] == pytest.approx(600)
    assert holding["market_value"] == pytest.approx(780)
    assert summary["realized_pnl"] == pytest.approx(80)
    assert summary["unrealized_pnl"] == pytest.approx(180)


def test_portfolio_rejects_oversell(tmp_path):
    _, service = build(tmp_path)
    service.add_transaction({"account":"Main","ticker":"AAPL","action":"BUY","occurred_at":"2026-01-01T10:00:00Z","quantity":2,"price":100,"fees":0})
    with pytest.raises(ValueError, match="Cannot sell"):
        service.add_transaction({"account":"Main","ticker":"AAPL","action":"SELL","occurred_at":"2026-01-02T10:00:00Z","quantity":3,"price":110,"fees":0})

def test_cannot_delete_buy_that_would_make_later_sale_invalid(tmp_path):
    _, service = build(tmp_path)
    buy = service.add_transaction({"account":"Main","ticker":"AAPL","action":"BUY","occurred_at":"2026-01-01T10:00:00Z","quantity":5,"price":100,"fees":0})
    service.add_transaction({"account":"Main","ticker":"AAPL","action":"SELL","occurred_at":"2026-01-02T10:00:00Z","quantity":3,"price":110,"fees":0})
    with pytest.raises(ValueError, match="Cannot sell"):
        service.delete_transaction(buy["id"])

class FakeExecutionPrices:
    def resolve(self, ticker, occurred_at, override=None):
        if override is not None:
            return {"price": float(override), "source": "manual_override", "overridden": True}
        return {"price": 200.0, "source": "test_1m_close_estimate", "timestamp": "2026-01-01T10:00:00+00:00", "overridden": False}


class FakeFx:
    def rate(self, from_currency, to_currency, at):
        return {"rate": 1.25, "source": "test_fx", "date": "2026-01-01"}

    def latest(self, from_currency, to_currency):
        return {"rate": 1.20, "source": "test_fx", "date": "2026-02-01"}


def test_amount_based_buy_resolves_price_fx_and_fractional_quantity(tmp_path):
    db = Database(tmp_path / "amount-ledger.db")
    db.initialize()
    with db.connect() as c:
        c.execute("INSERT INTO securities(ticker,name,provider) VALUES ('AAPL','Apple','test')")
    service = PortfolioService(PortfolioRepository(db), ScreenerRepository(db), FakeScreener(), FakeExecutionPrices(), FakeFx())
    tx = service.add_transaction({
        "account":"Main", "ticker":"AAPL", "action":"BUY", "occurred_at":"2026-01-01T10:00:00Z",
        "input_mode":"amount", "amount":100, "base_currency":"GBP", "asset_currency":"USD", "fees":1,
    })
    assert tx["price"] == pytest.approx(200)
    assert tx["quantity"] == pytest.approx(0.625)
    assert tx["input_amount"] == pytest.approx(100)
    assert tx["fx_rate"] == pytest.approx(1.25)
    assert tx["price_overridden"] == 0


def test_amount_based_portfolio_reports_base_currency_return(tmp_path):
    db = Database(tmp_path / "base-ledger.db")
    db.initialize()
    with db.connect() as c:
        c.execute("INSERT INTO securities(ticker,name,provider) VALUES ('AAPL','Apple','test')")
    service = PortfolioService(PortfolioRepository(db), ScreenerRepository(db), FakeScreener(), FakeExecutionPrices(), FakeFx())
    service.add_transaction({
        "account":"Main", "ticker":"AAPL", "action":"BUY", "occurred_at":"2026-01-01T10:00:00Z",
        "input_mode":"amount", "amount":100, "base_currency":"GBP", "asset_currency":"USD", "fees":0,
    })
    with db.connect() as c:
        c.execute("INSERT INTO market_snapshots(ticker,price,timestamp,source) VALUES ('AAPL',240,'2026-02-02T10:00:00Z','test')")
    summary = service.summary("Main")
    # 0.625 shares * $240 = $150; at $1.20/GBP that is £125 vs £100 cost.
    assert summary["base_market_value"] == pytest.approx(125)
    assert summary["base_unrealized_pnl"] == pytest.approx(25)
    assert summary["base_unrealized_return_pct"] == pytest.approx(25)
