from types import SimpleNamespace

import pandas as pd
import pytest

from app.backtesting.strategies.reference import EmaCrossReference, OpeningRangeBreakoutReference
from app.services.backtest import BacktestService
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database


class FakeMarketData:
    def __init__(self, frame):
        self.frame = frame
        self.provider = SimpleNamespace(
            historical_delay_minutes=0, historical_feed="sip", adjustment="split"
        )

    def get_bars(self, symbol, timeframe, start, end):
        frame = self.frame.copy()
        ts = pd.to_datetime(frame["timestamp"], utc=True)
        return frame[(ts >= pd.Timestamp(start)) & (ts <= pd.Timestamp(end))].reset_index(drop=True)


def sample_frame():
    rows = []
    # Prior session context plus replay session. UTC is EDT+4 in June.
    for day in ("2026-06-01", "2026-06-02"):
        start = pd.Timestamp(f"{day}T13:30:00Z")
        for i in range(78):
            ts = start + pd.Timedelta(minutes=5 * i)
            price = 100 + i * 0.05 + (0 if day.endswith("01") else 2)
            rows.append([ts, price, price + .2, price - .2, price + .05, 1000 + i])
    return pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])


def test_strategy_owned_values_are_available_only_as_research_parameters():
    normal = {p.key for p in EmaCrossReference.spec.parameters}
    research = {p.key for p in EmaCrossReference.spec.research_parameters}
    assert "target_rr" not in normal
    assert "stop_atr" not in normal
    assert {"target_rr", "stop_atr"}.issubset(research)
    assert "target_rr" in {p.key for p in OpeningRangeBreakoutReference.spec.research_parameters}


def test_research_override_can_temporarily_change_reference_target():
    strategy = EmaCrossReference(target_rr=2.75, stop_atr=1.25)
    assert strategy.params["target_rr"] == pytest.approx(2.75)
    assert strategy.params["stop_atr"] == pytest.approx(1.25)
    assert EmaCrossReference.TARGET_RR == 2.0  # source default stays untouched


def test_saved_validation_experiment_can_be_reopened_without_rerun(tmp_path):
    db = Database(tmp_path / "ledger.db"); db.initialize()
    repo = BacktestRunRepository(db)
    service = BacktestService(None, repo)
    for role, value in (("development", .2), ("validation", .1), ("out_of_sample", -.1)):
        repo.create(
            config={"strategy_key": "ema_cross_reference", "symbols": ["AAPL"], "start_date": "2026-01-01", "end_date": "2026-01-31", "primary_timeframe": "5m", "session": "regular"},
            result={"strategy": {"key": "ema_cross_reference", "name": "EMA", "params": {}}, "symbols": ["AAPL"], "primary_timeframe": "5m", "session": "regular", "metrics": {"trades": 10, "expectancy_r": value, "total_r": value * 10, "net_pnl": value * 100, "return_pct": value, "max_drawdown_pct": -1}},
            name=f"Suite · {role}", notes="frozen rules", test_role=role,
            experiment_group="suite-001", tags=["validation-suite"],
        )
    suite = service.get_experiment("suite-001")
    assert suite["experiment_group"] == "suite-001"
    assert [run["test_role"] for run in suite["runs"]] == ["development", "validation", "out_of_sample"]
    assert suite["runs"][1]["result"]["metrics"]["expectancy_r"] == pytest.approx(.1)


def test_replay_uses_real_context_bar_count_and_reveal_boundary():
    service = BacktestService(FakeMarketData(sample_frame()))
    replay = service.replay_bars(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(), start_time="09:40", context_bars=30,
    )
    assert replay["initial_visible_count"] == 31  # 30 completed context bars + the replay-start bar
    visible = replay["bars"][:replay["initial_visible_count"]]
    assert len([b for b in visible if str(b["timestamp"]).startswith("2026-06-01")]) == 28
    assert str(visible[-1]["timestamp"]).startswith("2026-06-02 13:40")
    assert replay["count"] > replay["initial_visible_count"]


def test_replay_indicator_uses_shared_causal_indicator_registry():
    service = BacktestService(FakeMarketData(sample_frame()))
    result = service.replay_indicator(
        symbol="AAPL", timeframe="5m", session="regular",
        replay_date=pd.Timestamp("2026-06-02").date(), start_time="09:40", context_bars=30,
        key="ema", params={"length": 10},
    )
    assert result["key"] == "ema"
    assert result["overlay"] is True
    assert len(result["values"]) > 0
