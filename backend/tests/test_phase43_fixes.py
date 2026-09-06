from pathlib import Path

import pandas as pd

from app.services.chart_data import prepare_chart_bars
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository


def test_planned_rr_is_separate_from_realised_r(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    service = JournalService(JournalRepository(db))
    trade = service.create_trade({
        "ticker": "AAPL", "direction": "long", "entry_price": 100,
        "stop_loss": 99, "take_profit": 102, "exit_price": 101,
        "position_amount": 1000, "fees": 0,
    })
    assert trade["planned_rr"] == 2.0
    assert trade["r_multiple"] == 1.0


def test_planned_rr_short(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    service = JournalService(JournalRepository(db))
    trade = service.create_trade({
        "ticker": "AAPL", "direction": "short", "entry_price": 100,
        "stop_loss": 101, "take_profit": 98, "exit_price": 99,
        "position_amount": 1000, "fees": 0,
    })
    assert trade["planned_rr"] == 2.0
    assert trade["r_multiple"] == 1.0


def test_regular_session_filter_uses_new_york_time():
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-08-20T13:00:00Z",  # 09:00 ET, exclude
            "2026-08-20T13:30:00Z",  # 09:30 ET, include
            "2026-08-20T19:30:00Z",  # 15:30 ET, include
            "2026-08-20T20:00:00Z",  # 16:00 ET, exclude
        ], utc=True),
        "open": [1,2,3,4], "high": [2,3,4,5], "low": [0,1,2,3],
        "close": [1.5,2.5,3.5,4.5], "volume": [10,20,30,40],
    })
    out, mode = prepare_chart_bars(frame, "30m", "regular")
    assert mode == "session_filtered"
    assert len(out) == 2
    assert out.iloc[0]["timestamp"] == pd.Timestamp("2026-08-20T13:30:00Z")


def test_hourly_aggregation_starts_at_regular_open():
    times = pd.date_range("2026-08-20T13:30:00Z", periods=4, freq="30min")
    frame = pd.DataFrame({
        "timestamp": times,
        "open": [100,101,102,103], "high": [101,102,103,104],
        "low": [99,100,101,102], "close": [100.5,101.5,102.5,103.5],
        "volume": [10,20,30,40],
    })
    out, mode = prepare_chart_bars(frame, "1h", "regular")
    assert mode == "session_aligned_from_30m"
    assert len(out) == 2
    assert out.iloc[0]["timestamp"] == pd.Timestamp("2026-08-20T13:30:00Z")
    assert out.iloc[0]["open"] == 100
    assert out.iloc[0]["close"] == 101.5
    assert out.iloc[0]["volume"] == 30
