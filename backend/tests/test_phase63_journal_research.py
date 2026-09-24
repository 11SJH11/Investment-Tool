from pathlib import Path
import sqlite3

import pytest

from app.data.providers.autochartist import AutochartistProvider
from app.services.journal import JournalService
from app.storage.database import Database
from app.storage.journal_repository import JournalRepository
from app.storage.research_repository import ResearchRepository
from app.backtesting.strategies.xau_liquidity_type3 import XauLiquiditySweepType3Baseline


def _journal(tmp_path: Path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    repo = JournalRepository(db)
    return db, repo, JournalService(repo)


def test_replay_external_id_is_idempotent(tmp_path):
    _, repo, service = _journal(tmp_path)
    payload = {
        "source": "replay",
        "external_provider": "ledger_replay",
        "external_id": "replay:XAUUSD:2026-09-01:abc",
        "ticker": "XAUUSD",
        "direction": "long",
        "entry_price": 4400,
        "exit_price": 4415,
        "quantity": 1,
        "stop_loss": 4390,
        "source_metadata": {"replay_date": "2026-09-01"},
    }

    first = service.create_trade(payload)
    second = service.create_trade(payload)

    assert first["id"] == second["id"]
    assert second["deduplicated"] is True
    assert first["source_metadata"]["replay_date"] == "2026-09-01"
    assert len(repo.list_trades(source="replay")) == 1


def test_broker_import_source_is_supported_and_requires_identity(tmp_path):
    _, repo, service = _journal(tmp_path)
    trade = service.create_trade({
        "source": "broker_oanda",
        "external_provider": "oanda",
        "external_id": "trade-123",
        "external_order_id": "order-456",
        "ticker": "XAUUSD",
        "direction": "short",
        "entry_price": 4410,
        "exit_price": 4400,
        "quantity": 2,
    })

    assert trade["source"] == "broker_oanda"
    assert trade["external_provider"] == "oanda"
    assert trade["external_id"] == "trade-123"
    assert trade["imported_at"]
    assert repo.get_by_external(source="broker_oanda", external_provider="oanda", external_id="trade-123")["id"] == trade["id"]

    with pytest.raises(ValueError, match="external_provider and external_id"):
        service.create_trade({"source": "broker_oanda", "ticker": "XAUUSD"})


def test_research_external_source_item_upserts_instead_of_duplicates(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    repo = ResearchRepository(db)

    first = repo.upsert_item({
        "source": "autochartist",
        "source_item_id": "signal-1",
        "item_type": "technical_signal",
        "instrument": "xauusd",
        "title": "Resistance breakout",
        "direction": "bullish",
        "confidence": 75,
        "metadata": {"target": 4447.3},
    })
    second = repo.upsert_item({
        "source": "autochartist",
        "source_item_id": "signal-1",
        "item_type": "technical_signal",
        "instrument": "XAUUSD",
        "title": "Resistance breakout updated",
        "direction": "bullish",
        "confidence": 76,
        "metadata": {"target": 4450.0},
    })

    assert first["id"] == second["id"]
    assert second["title"] == "Resistance breakout updated"
    assert second["instrument"] == "XAUUSD"
    assert second["metadata"]["target"] == 4450.0
    assert len(repo.list_items(instrument="XAUUSD")) == 1



def test_phase63_migrates_old_journal_without_losing_rows(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE journal_trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL CHECK(source IN ('live_manual','paper_manual','replay','backtest')),
            name TEXT NOT NULL DEFAULT 'Trade', account TEXT NOT NULL DEFAULT 'Main', ticker TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'long', status TEXT NOT NULL DEFAULT 'open', opened_at TEXT, closed_at TEXT,
            entry_price REAL, exit_price REAL, quantity REAL, stop_loss REAL, take_profit REAL, fees REAL NOT NULL DEFAULT 0,
            result TEXT, result_source TEXT, pnl_amount REAL, pnl_pct REAL, r_multiple REAL, trade_type TEXT NOT NULL DEFAULT '',
            setup TEXT NOT NULL DEFAULT '', market_condition TEXT NOT NULL DEFAULT '', entry_timeframe TEXT NOT NULL DEFAULT '',
            timeframe_alignment TEXT NOT NULL DEFAULT '', dxy TEXT NOT NULL DEFAULT '', session_time TEXT NOT NULL DEFAULT '',
            tf_type TEXT NOT NULL DEFAULT '', wick TEXT NOT NULL DEFAULT '', analysis TEXT NOT NULL DEFAULT '',
            entry_notes TEXT NOT NULL DEFAULT '', management TEXT NOT NULL DEFAULT '', learning TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', timeframe_notes TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute("INSERT INTO journal_trades(source,ticker,entry_price) VALUES ('paper_manual','XAUUSD',4400)")
    connection.commit()
    connection.close()

    db = Database(path)
    db.initialize()
    with db.connect() as migrated:
        row = migrated.execute("SELECT ticker, entry_price FROM journal_trades WHERE id=1").fetchone()
        assert tuple(row) == ("XAUUSD", 4400)
        columns = {r[1] for r in migrated.execute("PRAGMA table_info(journal_trades)")}
        assert {"external_provider", "external_id", "external_order_id", "source_metadata", "imported_at", "practised_at"} <= columns
        migrated.execute(
            "INSERT INTO journal_trades(source,ticker,external_provider,external_id) VALUES ('broker_oanda','XAUUSD','oanda','legacy-test')"
        )
        assert migrated.execute("SELECT COUNT(*) FROM journal_trades").fetchone()[0] == 2

def test_autochartist_scaffold_never_probes_or_scrapes_by_itself():
    provider = AutochartistProvider(enabled=False, broker_id="", user="", secret_key="")
    report = provider.capability_report()
    assert report["configured"] is False
    assert report["remote_probe_performed"] is False
    assert report["status"] == "not_configured"

    configured = AutochartistProvider(
        enabled=True,
        broker_id="broker",
        user="user",
        account_type="LIVE",
        secret_key="secret",
    )
    configured_report = configured.capability_report()
    assert configured_report["configured"] is True
    assert configured_report["remote_probe_performed"] is False
    assert configured_report["status"] == "credentials_present_not_validated"
    with pytest.raises(RuntimeError, match="approved developer API contract"):
        configured.fetch_items()


def test_xau_baseline_v11_identity_and_structure_parameters_are_stable():
    spec = XauLiquiditySweepType3Baseline.spec
    assert spec.key == "xau_liquidity_type3_baseline_v1"
    assert "v1.1" in spec.name
    assert spec.defaults["structure_lookback_bars"] == 40
    assert spec.defaults["minimum_structure_bars"] == 3
    assert spec.defaults["target_r"] == 1.5
    assert spec.defaults["entry_retrace"] == 0.5
