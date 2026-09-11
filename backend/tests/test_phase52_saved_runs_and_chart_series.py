import json

import pandas as pd

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig, EntrySignal
from app.backtesting.strategies.base import Strategy, StrategySpec
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database


class HoldToEnd(Strategy):
    spec = StrategySpec(key="hold52", name="Hold", defaults={}, timeframes=("5m",))
    def __init__(self, **params):
        super().__init__(**params)
        self.done = False
    def reset(self):
        self.done = False
    def on_bar(self, ctx):
        if not self.done and ctx.position is None:
            self.done = True
            close = float(ctx.current_bar["close"])
            return EntrySignal("long", stop_loss=close - 50, take_profit=close + 100, reason="hold_to_end")
        return None


def frame(rows):
    return pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"]).assign(
        timestamp=lambda x: pd.to_datetime(x.timestamp, utc=True)
    )


def test_overnight_end_of_data_equity_curve_has_unique_strict_timestamps():
    result = BacktestEngine(BacktestConfig(starting_balance=10_000, sizing_mode="quantity", risk_value=1, allow_overnight=True)).run(
        symbol_frames={"AAPL": {"5m": frame([
            ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
            ["2026-01-02T14:35:00Z",100,101.0,99.5,100.5,10],
        ])}},
        strategies={"AAPL": HoldToEnd()},
        primary_timeframe="5m",
    )
    timestamps = [pd.Timestamp(point["timestamp"]) for point in result["equity_curve"]]
    assert timestamps == sorted(timestamps)
    assert len(timestamps) == len(set(timestamps))
    assert result["trades"][0]["exit_reason"] == "end_of_data"
    assert result["equity_curve"][-1]["closed_trades"][0]["exit_reason"] == "end_of_data"


def test_equity_curve_exposes_return_and_cumulative_r_for_chart_modes():
    result = BacktestEngine(BacktestConfig(starting_balance=10_000, sizing_mode="quantity", risk_value=1, allow_overnight=True)).run(
        symbol_frames={"AAPL": {"5m": frame([
            ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
            ["2026-01-02T14:35:00Z",100,103,99.5,102,10],
        ])}},
        strategies={"AAPL": HoldToEnd()},
        primary_timeframe="5m",
    )
    last = result["equity_curve"][-1]
    assert "return_pct" in last
    assert "cumulative_r" in last


def test_saved_run_repository_round_trips_config_and_immutable_result(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    repo = BacktestRunRepository(db)
    config = {
        "strategy_key": "ema_cross_reference", "symbols": ["AAPL"],
        "start_date": "2026-01-01", "end_date": "2026-02-01",
        "primary_timeframe": "5m", "session": "regular", "allow_overnight": False,
    }
    result = {
        "strategy": {"key": "ema_cross_reference", "name": "EMA Cross · reference", "params": {}},
        "symbols": ["AAPL"], "primary_timeframe": "5m", "session": "regular",
        "start": "2026-01-01T05:00:00+00:00", "end": "2026-02-02T05:00:00+00:00",
        "metrics": {"trades": 12, "expectancy_r": 0.15, "total_r": 1.8, "net_pnl": 90, "return_pct": 0.9, "max_drawdown_pct": -2.1},
        "trades": [{"symbol": "AAPL"}], "equity_curve": [{"timestamp": "2026-01-01T14:35:00+00:00", "equity": 10000}],
    }
    saved = repo.create(config=config, result=result, name="Baseline", notes="Do not tune OOS", test_role="validation")
    assert saved["name"] == "Baseline"
    assert saved["test_role"] == "validation"
    assert saved["config"]["allow_overnight"] is False
    assert saved["result"]["metrics"]["total_r"] == 1.8
    summary = repo.list()[0]
    assert summary["symbols"] == ["AAPL"]
    assert summary["expectancy_r"] == 0.15

    updated = repo.update_metadata(saved["id"], name="Baseline v1", test_role="out_of_sample")
    assert updated["name"] == "Baseline v1"
    assert updated["result"]["metrics"]["trades"] == 12
    repo.delete(saved["id"])
    assert repo.list() == []


def test_database_phase52_schema_contains_saved_runs_table(tmp_path):
    db = Database(tmp_path / "ledger.db")
    db.initialize()
    with db.connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        versions = {row[0] for row in connection.execute("SELECT version FROM schema_version").fetchall()}
    assert "backtest_runs" in tables
    assert 13 in versions
