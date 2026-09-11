from fastapi.testclient import TestClient

from app.main import app


def test_strategy_lab_lists_plugins_without_market_keys():
    with TestClient(app) as client:
        strategies = client.get("/api/strategy-lab/strategies")
        indicators = client.get("/api/strategy-lab/indicators")
    assert strategies.status_code == 200
    keys = {item["key"] for item in strategies.json()["strategies"]}
    assert "ema_cross_reference" in keys
    assert "opening_range_breakout_reference" in keys
    assert indicators.status_code == 200
    indicator_keys = {item["key"] for item in indicators.json()["indicators"]}
    assert {"sma", "ema", "rsi", "atr", "vwap"}.issubset(indicator_keys)


def test_phase51_backtest_request_accepts_schedule_and_guardrails():
    from app.api.strategy_lab import BacktestRequest

    request = BacktestRequest(
        strategy_key="ema_cross_reference",
        symbols=["AAPL"],
        start_date="2026-01-01",
        end_date="2026-02-01",
        entry_windows=[{"start":"09:30","end":"11:00"},{"start":"14:00","end":"15:30"}],
        trading_weekdays=[0,1,2,3,4],
        allow_overnight=False,
        force_close_time="15:55",
        max_trades_per_day=3,
        max_daily_loss_r=2.0,
        max_consecutive_losses=2,
        cooldown_minutes=15,
        spread_bps=1.5,
    )
    payload = request.model_dump()
    assert payload["entry_windows"][1]["start"] == "14:00"
    assert payload["allow_overnight"] is False
    assert payload["max_daily_loss_r"] == 2.0
