import pytest
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


def build(tmp_path):
    db=Database(tmp_path/'ledger.db'); db.initialize(); repo=JournalRepository(db); return repo, JournalService(repo)


def test_journal_report_filters_and_breakdowns(tmp_path):
    repo, service = build(tmp_path)
    service.create_trade({"source":"paper_manual","ticker":"AAPL","direction":"long","opened_at":"2026-08-03T13:35:00+00:00","closed_at":"2026-08-03T14:00:00+00:00","entry_price":100,"exit_price":104,"quantity":1,"stop_loss":98,"take_profit":104,"setup":"Pullback","entry_timeframe":"5m","market_condition":"Trending"})
    service.create_trade({"source":"paper_manual","ticker":"MSFT","direction":"short","opened_at":"2026-08-04T15:10:00+00:00","closed_at":"2026-08-04T16:10:00+00:00","entry_price":100,"exit_price":102,"quantity":1,"stop_loss":101,"take_profit":98,"setup":"Breakdown","entry_timeframe":"15m","market_condition":"Range"})
    report=repo.report({"ticker":"AAPL"})
    assert report["summary"]["trades"] == 1
    assert report["summary"]["average_r"] == pytest.approx(2.0)
    assert report["breakdowns"]["symbol"][0]["symbol"] == "AAPL"
    full=repo.report({})
    assert full["summary"]["trades"] == 2
    assert {x["direction"] for x in full["breakdowns"]["direction"]} == {"long","short"}
