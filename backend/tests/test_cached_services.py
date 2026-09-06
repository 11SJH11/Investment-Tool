from app.services.fundamentals import FundamentalsService
from app.services.macro import MacroService
from app.storage.database import Database
from app.storage.json_cache import JsonCacheRepository


class FakeFundamentals:
    key = "fake-sec"

    def __init__(self):
        self.calls = 0

    def get_fundamentals(self, ticker):
        self.calls += 1
        return {"ticker": ticker, "revenue": self.calls}


class FakeMacro:
    key = "fake-fred"

    def __init__(self):
        self.calls = 0

    def get_snapshot(self):
        self.calls += 1
        return {"call": self.calls}


def test_fundamentals_service_uses_cache_until_refresh(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    provider = FakeFundamentals()
    service = FundamentalsService(provider, JsonCacheRepository(db), ttl_seconds=3600)

    assert service.get("AAPL")["revenue"] == 1
    assert service.get("AAPL")["revenue"] == 1
    assert service.get("AAPL", refresh=True)["revenue"] == 2
    assert provider.calls == 2


def test_macro_service_uses_cache_until_refresh(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    provider = FakeMacro()
    service = MacroService(provider, JsonCacheRepository(db), ttl_seconds=3600)

    assert service.get_snapshot()["call"] == 1
    assert service.get_snapshot()["call"] == 1
    assert service.get_snapshot(refresh=True)["call"] == 2
    assert provider.calls == 2
