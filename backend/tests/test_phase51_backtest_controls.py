import pandas as pd
import pytest

from app.backtesting.engine import BacktestEngine, calculate_analysis
from app.backtesting.models import BacktestConfig, BacktestTrade, EntrySignal
from app.backtesting.strategies.base import Strategy, StrategySpec


class AlwaysLong(Strategy):
    spec = StrategySpec(key="always", name="Always", defaults={}, timeframes=("5m",))
    def on_bar(self, ctx):
        if ctx.position is None:
            close = float(ctx.current_bar["close"])
            return EntrySignal("long", stop_loss=close - 10, take_profit=close + 20, reason="test_signal")
        return None


class OneLong(Strategy):
    spec = StrategySpec(key="one51", name="One", defaults={}, timeframes=("5m",))
    def __init__(self, **params):
        super().__init__(**params); self.done = False
    def reset(self): self.done = False
    def on_bar(self, ctx):
        if not self.done and ctx.position is None:
            self.done = True
            close = float(ctx.current_bar["close"])
            return EntrySignal("long", stop_loss=close - 10, take_profit=close + 20, reason="test_signal")
        return None


def frame(rows):
    return pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"]).assign(timestamp=lambda x: pd.to_datetime(x.timestamp, utc=True))


def run(rows, strategy=None, **config):
    engine = BacktestEngine(BacktestConfig(starting_balance=10_000, sizing_mode="quantity", risk_value=1, **config))
    strategy = strategy or AlwaysLong()
    return engine.run(symbol_frames={"AAPL":{"5m":frame(rows)}}, strategies={"AAPL":strategy}, primary_timeframe="5m")


def test_custom_entry_window_controls_fill_time_in_new_york():
    # January: 15:00Z == 10:00 ET. Earlier signals are rejected until the
    # 10:00 ET window opens, then the next-bar-open contract is preserved.
    result = run([
        ["2026-01-02T14:50:00Z",100,100.5,99.5,100,10],  # 09:50 ET
        ["2026-01-02T14:55:00Z",100,100.5,99.5,100,10],  # decision 10:00 ET
        ["2026-01-02T15:00:00Z",101,101.5,100.5,101,10], # fill 10:00 ET
        ["2026-01-02T15:05:00Z",101,101.5,100.5,101,10],
    ], entry_windows=(("10:00", "11:00"),))
    assert result["trades"][0]["entry_time"].startswith("2026-01-02T15:00")
    assert any(item["reason"] == "outside_entry_window" for item in result["rejected_signals"])


def test_no_overnight_forces_session_close_on_final_bar():
    result = run([
        ["2026-01-02T20:45:00Z",100,100.5,99.5,100,10], # 15:45 ET signal
        ["2026-01-02T20:50:00Z",100,100.4,99.8,100.2,10], # entry
        ["2026-01-02T20:55:00Z",100.2,100.6,100.0,100.4,10], # final 5m bar
    ], strategy=OneLong(), allow_overnight=False, session_end="16:00")
    trade = result["trades"][0]
    assert trade["exit_reason"] == "session_close"
    assert trade["exit_time"].startswith("2026-01-02T21:00")
    assert result["execution_model"]["allow_overnight"] is False


def test_custom_force_close_time_closes_at_requested_bar_end():
    result = run([
        ["2026-01-02T20:35:00Z",100,100.5,99.5,100,10], # 15:35
        ["2026-01-02T20:40:00Z",100,100.4,99.8,100.2,10], # entry 15:40
        ["2026-01-02T20:45:00Z",100.2,100.5,100.0,100.3,10],
        ["2026-01-02T20:50:00Z",100.3,100.6,100.1,100.4,10], # closes 15:55
        ["2026-01-02T20:55:00Z",100.4,100.7,100.2,100.5,10],
    ], strategy=OneLong(), allow_overnight=False, force_close_time="15:55", session_end="16:00")
    assert result["trades"][0]["exit_time"].startswith("2026-01-02T20:55")
    assert result["trades"][0]["exit_reason"] == "session_close"


def test_spread_is_explicit_adverse_execution_assumption():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
        ["2026-01-02T14:35:00Z",100,100.5,99.5,100,10],
    ], strategy=OneLong(), spread_bps=20)
    # Full 20 bps spread => half spread (10 bps) applied to market entry.
    assert result["trades"][0]["entry_price"] == pytest.approx(100.10)
    assert result["execution_model"]["spread_bps"] == 20


def test_analysis_exposes_explanatory_breakdowns_not_just_totals():
    trades = [
        BacktestTrade("AAPL","long",pd.Timestamp("2026-01-05T14:35Z").to_pydatetime(),pd.Timestamp("2026-01-05T15:00Z").to_pydatetime(),100,102,1,99,102,1,2,0,2,2,2,2,"win","target","bull",{}),
        BacktestTrade("AAPL","short",pd.Timestamp("2026-01-06T15:35Z").to_pydatetime(),pd.Timestamp("2026-01-06T16:00Z").to_pydatetime(),100,101,1,101,98,1,-1,0,-1,-1,-1,2,"loss","stop","bear",{}),
    ]
    from zoneinfo import ZoneInfo
    analysis = calculate_analysis(trades, ZoneInfo("America/New_York"))
    assert {row["direction"] for row in analysis["breakdowns"]["direction"]} == {"long", "short"}
    assert analysis["breakdowns"]["weekday"][0]["weekday"] == "Monday"
    assert analysis["largest_losses"][0]["r_multiple"] == -1
    assert "validation" in analysis["note"].lower()


def test_fixed_cash_position_sizing_is_supported():
    engine = BacktestEngine(BacktestConfig(starting_balance=10_000, sizing_mode="cash_position", risk_value=1_000))
    result = engine.run(
        symbol_frames={"AAPL":{"5m":frame([
            ["2026-01-02T14:30:00Z",100,100.5,99.5,100,10],
            ["2026-01-02T14:35:00Z",100,100.5,99.5,100,10],
        ])}},
        strategies={"AAPL":OneLong()}, primary_timeframe="5m",
    )
    assert result["trades"][0]["quantity"] == pytest.approx(10.0)

class ReenterLong(Strategy):
    spec = StrategySpec(key="reenter51", name="Reenter", defaults={}, timeframes=("5m",))
    def on_bar(self, ctx):
        if ctx.position is None:
            close = float(ctx.current_bar["close"])
            return EntrySignal("long", stop_loss=close - 1, take_profit=close + 1, reason="repeat")
        return None


def test_max_trades_per_day_blocks_additional_entries():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.1,99.9,100,10],
        ["2026-01-02T14:35:00Z",100,101.5,99.9,101,10],  # trade 1 target
        ["2026-01-02T14:40:00Z",101,101.1,100.9,101,10],
        ["2026-01-02T14:45:00Z",101,102.5,100.9,102,10],  # trade 2 target
        ["2026-01-02T14:50:00Z",102,102.1,101.9,102,10],
        ["2026-01-02T14:55:00Z",102,103.5,101.9,103,10],
    ], strategy=ReenterLong(), max_trades_per_day=2)
    assert len(result["trades"]) == 2
    assert any(item["reason"] == "max_trades_per_day" for item in result["rejected_signals"])
    assert any(item["reason"] == "max_trades_per_day" and item["count"] >= 1 for item in result["rejected_signal_summary"])


def test_daily_loss_limit_blocks_new_entries_after_realised_r_threshold():
    result = run([
        ["2026-01-02T14:30:00Z",100,100.1,99.9,100,10],
        ["2026-01-02T14:35:00Z",100,100.1,98.5,99,10],   # trade 1 stop = -1R
        ["2026-01-02T14:40:00Z",99,99.1,98.9,99,10],
        ["2026-01-02T14:45:00Z",99,99.1,97.5,98,10],     # trade 2 stop = -1R
        ["2026-01-02T14:50:00Z",98,98.1,97.9,98,10],
        ["2026-01-02T14:55:00Z",98,99,97.9,98.5,10],
    ], strategy=ReenterLong(), max_daily_loss_r=2.0)
    assert len(result["trades"]) == 2
    assert any(item["reason"] == "daily_loss_limit" for item in result["rejected_signals"])
