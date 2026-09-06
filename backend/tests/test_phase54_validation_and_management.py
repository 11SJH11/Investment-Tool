import sqlite3

import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig, EntrySignal, ManagePositionSignal
from app.backtesting.strategies.base import Strategy, StrategySpec
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database


class ManagedLong(Strategy):
    spec = StrategySpec(key="managed54", name="Managed", defaults={}, timeframes=("5m",))

    def __init__(self, **params):
        super().__init__(**params)
        self.entered = False

    def reset(self):
        self.entered = False

    def on_bar(self, ctx):
        if ctx.position is None and not self.entered:
            self.entered = True
            return EntrySignal("long", stop_loss=99.0, take_profit=110.0, reason="entry")
        if ctx.position is not None and not ctx.position.metadata.get("managed"):
            return ManagePositionSignal(
                new_stop_loss=100.0,
                reduce_fraction=0.5,
                reason="take_half_and_breakeven",
                metadata={"managed": True},
            )
        return None


def frame(rows):
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"]).assign(
        timestamp=lambda x: pd.to_datetime(x.timestamp, utc=True)
    )


def test_partial_exit_and_breakeven_remain_one_logical_trade():
    result = BacktestEngine(BacktestConfig(
        starting_balance=10_000, sizing_mode="quantity", risk_value=1, allow_overnight=True,
    )).run(
        symbol_frames={"AAPL": {"5m": frame([
            ["2026-01-02T14:30:00Z", 100, 100.5, 99.5, 100, 10],
            ["2026-01-02T14:35:00Z", 100, 102.5, 99.8, 102, 10],
            ["2026-01-02T14:40:00Z", 102, 103, 101, 102.5, 10],
            ["2026-01-02T14:45:00Z", 102.5, 103, 99.5, 100, 10],
        ])}},
        strategies={"AAPL": ManagedLong()}, primary_timeframe="5m",
    )
    assert result["metrics"]["trades"] == 1
    trade = result["trades"][0]
    assert trade["quantity"] == pytest.approx(1.0)
    assert trade["stop_loss"] == pytest.approx(99.0)  # original planned stop stays in trade record
    assert trade["metadata"]["final_stop_loss"] == pytest.approx(100.0)
    assert len(trade["metadata"]["partial_exits"]) == 1
    assert trade["metadata"]["partial_exits"][0]["quantity"] == pytest.approx(0.5)
    assert trade["exit_price"] == pytest.approx(101.0)  # weighted: half at 102, half at 100
    assert trade["gross_pnl"] == pytest.approx(1.0)
    assert trade["r_multiple"] == pytest.approx(1.0)


def test_partial_exit_commissions_are_counted_once_per_fill():
    result = BacktestEngine(BacktestConfig(
        starting_balance=10_000, sizing_mode="quantity", risk_value=1,
        commission_per_order=1.0, allow_overnight=True,
    )).run(
        symbol_frames={"AAPL": {"5m": frame([
            ["2026-01-02T14:30:00Z", 100, 100.5, 99.5, 100, 10],
            ["2026-01-02T14:35:00Z", 100, 102.5, 99.8, 102, 10],
            ["2026-01-02T14:40:00Z", 102, 103, 101, 102.5, 10],
            ["2026-01-02T14:45:00Z", 102.5, 103, 99.5, 100, 10],
        ])}},
        strategies={"AAPL": ManagedLong()}, primary_timeframe="5m",
    )
    trade = result["trades"][0]
    assert trade["gross_pnl"] == pytest.approx(1.0)
    assert trade["fees"] == pytest.approx(3.0)  # entry + partial exit + final exit
    assert trade["net_pnl"] == pytest.approx(-2.0)
    assert result["metrics"]["ending_balance"] == pytest.approx(9998.0)


def test_phase54_saved_runs_store_experiment_group_and_tags(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    repo = BacktestRunRepository(db)
    config = {
        "strategy_key": "ema_cross_reference", "symbols": ["AAPL"],
        "start_date": "2026-01-01", "end_date": "2026-03-01", "primary_timeframe": "5m", "session": "regular",
    }
    result = {
        "strategy": {"key": "ema_cross_reference", "name": "EMA Cross · reference", "params": {}},
        "symbols": ["AAPL"], "primary_timeframe": "5m", "session": "regular",
        "metrics": {"trades": 10, "expectancy_r": 0.1, "total_r": 1.0, "net_pnl": 40, "return_pct": 0.4, "max_drawdown_pct": -1.2},
    }
    saved = repo.create(
        config=config, result=result, test_role="validation", experiment_group="ema-baseline-001",
        tags=["baseline", "AAPL", "baseline"],
    )
    assert saved["experiment_group"] == "ema-baseline-001"
    assert saved["tags"] == ["baseline", "AAPL"]
    summary = repo.list()[0]
    assert summary["experiment_group"] == "ema-baseline-001"
    assert summary["tags"] == ["baseline", "AAPL"]
    assert 14 in {row[0] for row in db.connect().execute("SELECT version FROM schema_version").fetchall()}


def test_phase54_migrates_existing_phase52_run_table(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE backtest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            test_role TEXT NOT NULL DEFAULT 'development', strategy_key TEXT NOT NULL,
            strategy_name TEXT NOT NULL, symbols TEXT NOT NULL DEFAULT '[]', start_date TEXT NOT NULL,
            end_date TEXT NOT NULL, primary_timeframe TEXT NOT NULL, session TEXT NOT NULL,
            config_json TEXT NOT NULL, result_json TEXT NOT NULL, trades INTEGER NOT NULL DEFAULT 0,
            expectancy_r REAL, total_r REAL, net_pnl REAL, return_pct REAL, max_drawdown_pct REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    connection.commit(); connection.close()
    db = Database(path); db.initialize()
    with db.connect() as connection:
        cols = {row[1] for row in connection.execute("PRAGMA table_info(backtest_runs)").fetchall()}
    assert {"experiment_group", "tags"}.issubset(cols)
