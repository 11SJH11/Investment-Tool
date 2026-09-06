from datetime import timezone

import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig, EntrySignal
from app.backtesting.strategies.base import Strategy, StrategySpec


class OneLong(Strategy):
    spec = StrategySpec(key="one", name="One", defaults={}, timeframes=("5m",))
    def __init__(self, **params):
        super().__init__(**params); self.done = False
    def reset(self): self.done = False
    def on_bar(self, ctx):
        if not self.done and ctx.position is None:
            self.done = True
            close = float(ctx.current_bar["close"])
            return EntrySignal("long", stop_loss=close - 1, take_profit=close + 2, reason="test")
        return None


def frame(rows):
    return pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"]).assign(timestamp=lambda x: pd.to_datetime(x.timestamp, utc=True))


def run(rows, **config):
    engine = BacktestEngine(BacktestConfig(starting_balance=10_000, sizing_mode="quantity", risk_value=1, **config))
    return engine.run(symbol_frames={"AAPL":{"5m":frame(rows)}}, strategies={"AAPL":OneLong()}, primary_timeframe="5m")


def test_signal_fills_next_bar_open_not_signal_close():
    result = run([
        ["2026-01-02T14:30:00Z",100,101,99.5,100,10],
        ["2026-01-02T14:35:00Z",101,101.5,100.5,101,10],
        ["2026-01-02T14:40:00Z",101,103,100.5,102,10],
    ])
    trade = result["trades"][0]
    assert trade["entry_price"] == 101
    assert trade["entry_time"].startswith("2026-01-02T14:35")


def test_same_bar_stop_and_target_defaults_to_stop_first():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,103,98,100,10],
    ])
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_same_bar"
    assert trade["r_multiple"] == pytest.approx(-1.0)


def test_target_first_policy_is_explicit_and_changes_ambiguous_bar():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,103,98,100,10],
    ], same_bar_policy="target_first")
    assert result["trades"][0]["exit_reason"] == "target_same_bar"
    assert result["trades"][0]["r_multiple"] == pytest.approx(2.0)


def test_gap_through_stop_fills_at_open_not_stop_price():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:40:00Z",98,99,97,98.5,10],
    ])
    trade = result["trades"][0]
    assert trade["exit_reason"] == "stop_gap"
    assert trade["exit_price"] == 98
    assert trade["r_multiple"] == pytest.approx(-2.0)


def test_initial_equity_is_part_of_drawdown_reference():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,100.2,98.5,99,10],
    ])
    assert result["metrics"]["max_drawdown_cash"] < 0
    assert result["metrics"]["max_drawdown_pct"] < 0


def test_commissions_are_applied_once_and_affect_ending_balance():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,103,99.5,102,10],
    ], commission_per_order=1.0)
    trade = result["trades"][0]
    assert trade["gross_pnl"] == pytest.approx(2.0)
    assert trade["fees"] == pytest.approx(2.0)
    assert trade["net_pnl"] == pytest.approx(0.0)
    assert result["metrics"]["ending_balance"] == pytest.approx(10_000.0)
