from pathlib import Path

import pytest

from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


def build(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    repo = JournalRepository(db)
    return repo, JournalService(repo)


def test_manual_trade_computes_result_and_metrics(tmp_path):
    _, service = build(tmp_path)
    trade = service.create_trade({
        "source":"live_manual", "ticker":"AAPL", "direction":"long",
        "entry_price":100, "exit_price":90, "quantity":2, "stop_loss":95, "fees":2,
        # Phase 4 values are ignored in favour of derived execution maths.
        "result":"win", "pnl_amount":25, "pnl_pct":2.5, "r_multiple":0.75,
    })
    assert trade["result"] == "loss"
    assert trade["result_source"] == "computed"
    assert trade["pnl_amount"] == pytest.approx(-22)
    assert trade["pnl_pct"] == pytest.approx(-11)
    assert trade["r_multiple"] == pytest.approx(-2.2)
    assert trade["status"] == "closed"


def test_replay_trade_computes_net_result_pnl_and_r(tmp_path):
    _, service = build(tmp_path)
    trade = service.create_trade({
        "source":"replay", "ticker":"AAPL", "direction":"long",
        "entry_price":100, "exit_price":110, "quantity":2, "stop_loss":95, "fees":2,
        "result":"loss", "pnl_amount":-999, "r_multiple":-99,
    })
    assert trade["result"] == "win"
    assert trade["result_source"] == "computed"
    assert trade["pnl_amount"] == pytest.approx(18)
    assert trade["pnl_pct"] == pytest.approx(9)
    assert trade["r_multiple"] == pytest.approx(1.8)


def test_manual_trade_can_be_edited_and_recalculated(tmp_path):
    _, service = build(tmp_path)
    trade = service.create_trade({
        "source":"paper_manual", "ticker":"AAPL", "direction":"long",
        "entry_price":100, "exit_price":95, "quantity":1, "stop_loss":95,
    })
    assert trade["result"] == "loss"
    updated = service.update_trade(trade["id"], {"exit_price":110})
    assert updated["result"] == "win"
    assert updated["pnl_amount"] == pytest.approx(10)
    assert updated["r_multiple"] == pytest.approx(2)


def test_broker_pnl_override_is_preserved_but_result_is_derived(tmp_path):
    _, service = build(tmp_path)
    trade = service.create_trade({
        "source":"live_manual", "ticker":"AAPL", "direction":"long",
        "entry_price":100, "exit_price":105, "quantity":10, "stop_loss":98,
        "pnl_override":47.5, "override_reason":"Broker FX/fees",
    })
    assert trade["pnl_amount"] == pytest.approx(47.5)
    assert trade["pnl_source"] == "manual_override"
    assert trade["result"] == "win"
    assert trade["r_multiple"] == pytest.approx(2.375)


def test_calendar_and_analytics_aggregate_trade_results(tmp_path):
    repo, service = build(tmp_path)
    service.create_trade({"source":"paper_manual","ticker":"AAPL","opened_at":"2026-08-10T09:00:00Z","closed_at":"2026-08-10T10:00:00Z","entry_price":100,"exit_price":110,"quantity":1,"stop_loss":95})
    service.create_trade({"source":"paper_manual","ticker":"MSFT","opened_at":"2026-08-10T11:00:00Z","closed_at":"2026-08-10T12:00:00Z","entry_price":100,"exit_price":95,"quantity":1,"stop_loss":90})
    days = repo.calendar("2026-08", "paper_manual")
    assert days[0]["trades"] == 2
    assert days[0]["wins"] == 1
    assert days[0]["losses"] == 1
    assert days[0]["pnl_amount"] == pytest.approx(5)
    analytics = repo.analytics("paper_manual")
    assert analytics["trades"] == 2
    assert analytics["win_rate"] == pytest.approx(50)
    assert analytics["total_r"] == pytest.approx(1.5)


def test_daily_review_upserts_same_day_account(tmp_path):
    repo, _ = build(tmp_path)
    repo.upsert_daily_review({"review_date":"2026-08-27","account":"Main","learnings":"First"})
    repo.upsert_daily_review({"review_date":"2026-08-27","account":"Main","learnings":"Updated"})
    items = repo.list_daily_reviews()
    assert len(items) == 1
    assert items[0]["learnings"] == "Updated"


def test_playbook_and_timeframe_notes_round_trip(tmp_path):
    repo, service = build(tmp_path)
    entry = repo.create_playbook({"title":"Type 3 Shift","rules":"Wait for confirmation"})
    assert entry["title"] == "Type 3 Shift"
    trade = service.create_trade({"source":"paper_manual","ticker":"XAUUSD","timeframe_notes":{"1m":"entry","15m":"context"}})
    loaded = repo.get_trade(trade["id"])
    assert loaded["timeframe_notes"]["1m"] == "entry"
    assert loaded["timeframe_notes"]["15m"] == "context"
