import json

import pandas as pd
import pytest

from app.backtesting.context import StrategyContext
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.backtesting.momentum_reporting import completed_daily_frame, annotate_result, BIAS_WARNING
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.momentum_vcp_breakout_baseline_v1 import (
    MomentumVcpBreakoutBaselineV1 as Momentum, DEFAULTS, KEY, confirmed_swing_low,
)
from app.services.backtest import BacktestService
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


@pytest.fixture
def fixture():
    # Hand-worked fixture, fixed before testing performance:
    # Fri Jan 5 breakout over 100; Mon Jan 8 open 101; confirmed stop 97.5;
    # risk/share 3.5; target 108; Tue Jan 9 target exit; exactly +2R before costs.
    dates = list(pd.bdate_range(end="2024-01-05", periods=261, tz="America/New_York"))
    dates += list(pd.date_range("2024-01-08", periods=2, tz="America/New_York"))
    rows = []
    for i, date in enumerate(dates):
        c = 50 + 45*i/229
        row = dict(timestamp=date, open=c, high=c+1, low=c-1, close=c, volume=1_000_000)
        if 230 <= i < 255:
            row.update(open=97, high=100, low=92, close=98, volume=1_000_000)
        if 255 <= i < 260:
            row.update(open=99, high=99.5, low=[98.2,98,97.5,98,98.2][i-255], close=99, volume=500_000)
        if i == 260:
            row.update(open=99.5, high=101.5, low=99, close=101, volume=1_200_000)
        if i == 261:
            row.update(open=101, high=102, low=100, close=101.5, volume=600_000)
        if i == 262:
            row.update(open=102, high=108.5, low=101, close=108, volume=600_000)
        rows.append(row)
    return completed_daily_frame(pd.DataFrame(rows), pd.Timestamp("2024-01-11", tz="UTC"))


def context(frame, index=260, decision_time=None):
    return StrategyContext(symbol="TEST", primary_timeframe="1d",
        decision_time=decision_time or frame.available_at.iloc[index].to_pydatetime(),
        frames={"1d": frame}, position=None, equity=10_000)


def signal(frame, **params):
    return Momentum(**params).on_bar(context(frame))


def run(frame, params=None, config=None, symbols=("TEST",)):
    frames = {s: {"1d": frame.copy()} for s in symbols}
    result = BacktestEngine(config or BacktestConfig()).run(symbol_frames=frames,
        strategies={s: Momentum(**(params or {})) for s in symbols}, primary_timeframe="1d")
    result.update(data={}, strategy={})
    annotate_result(result, frames, {**DEFAULTS, **(params or {})})
    return result


def test_hand_worked_fixture_exactly(fixture):
    result = run(fixture)
    assert len(result["trades"]) == 1
    t = result["trades"][0]
    s = result["setups"][0]
    assert s["metadata"]["breakout_date"] == "2024-01-05"
    assert s["metadata"]["pivot"] == 100
    assert s["detected_at"] == "2024-01-06T05:00:00+00:00"
    assert t["entry_time"] == "2024-01-08T14:30:00+00:00"
    assert (t["entry_price"], t["stop_loss"], t["take_profit"]) == (101, 97.5, 108)
    assert (t["exit_time"], t["exit_price"], t["exit_reason"], t["r_multiple"]) == ("2024-01-09T14:30:00+00:00",108,"target",2)
    assert s["outcome"]["entered"] is True
    assert t["metadata"]["mfe_r_lower_bound"] == 2
    assert t["metadata"]["bars_in_trade"] == 2
    assert t["metadata"]["parameters"] == DEFAULTS
    json.dumps(result, allow_nan=False)


def test_registry_and_valid_trend_stack(fixture):
    strategy = strategy_registry.create(KEY)
    s = strategy.on_bar(context(fixture))
    m = s.metadata
    assert 101 > m["ema_fast"] > m["ema_medium"] > m["sma_long"] > m["sma_slope_comparison"]
    assert m["ema_medium"] == fixture.close.iloc[:261].ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1]


@pytest.mark.parametrize("fast,medium,long,before", [(101,95,90,89),(99,100,90,89),(99,95,96,90),(99,95,90,90),(99,95,90,91)])
def test_invalid_trend_and_non_rising_sma(fixture, fast, medium, long, before):
    ctx = context(fixture)
    def indicator(key, **params):
        if key == "ema":
            return pd.Series([fast if params["length"] == 20 else medium]*261)
        values = [long]*261
        values[-21] = before
        return pd.Series(values)
    ctx.indicator = indicator
    assert Momentum().on_bar(ctx) is None


def test_minimum_250_prior_bars(fixture):
    frame = fixture.iloc[11:].reset_index(drop=True)
    assert Momentum().on_bar(context(frame, 249)) is None
    frame = fixture.iloc[10:].reset_index(drop=True)
    assert Momentum().on_bar(context(frame, 250)) is not None


def test_liquidity_boundary_uses_prior_dollar_volume(fixture):
    value = float((fixture.iloc[240:260].close * fixture.iloc[240:260].volume).mean())
    assert signal(fixture, min_dollar_volume=value)
    assert signal(fixture, min_dollar_volume=value+1) is None
    fixture.loc[260,"volume"] *= 100
    assert signal(fixture, min_dollar_volume=value+1) is None


@pytest.mark.parametrize("length", [10,30])
def test_base_length_inclusive_bounds(fixture, length):
    assert signal(fixture, base_min=length, base_max=length).metadata["base_length"] == length


def test_longest_base_and_depth_boundary(fixture):
    s = signal(fixture, max_base_depth_pct=8)
    assert s.metadata["base_length"] == 30
    assert s.metadata["base_depth_pct"] == 8
    assert signal(fixture, max_base_depth_pct=7.999) is None


def test_pivot_is_causal_and_excludes_breakout(fixture):
    fixture.loc[260,"high"] = 500
    assert signal(fixture).metadata["pivot"] == 100
    fixture.loc[260,"close"] = 100
    assert signal(fixture) is None


def test_base_selection_is_fixed_before_observing_breakout_close(fixture):
    fixture.loc[230,"high"] = 102
    # A shorter base has pivot 100, but the preselected 30-bar base has 102.
    # N closes 101: do not switch to an easier pivot to manufacture a breakout.
    assert signal(fixture) is None
    assert signal(fixture,base_min=10,base_max=10).metadata["pivot"] == 100
    fixture.loc[260,"close"] = 103
    fixture.loc[260,"high"] = 104
    assert signal(fixture).metadata["pivot"] == 102


def test_volatility_contraction_pass_fail_and_formula(fixture):
    s = signal(fixture)
    m = s.metadata
    # First recent TR includes the gap above prior close 98: 99.5 - 98 = 1.5.
    expected_recent = sum([100*1.5/98,100*1.5/99,100*2/99,100*1.5/99,100*1.3/99])/5
    assert m["recent_atr_pct"] == pytest.approx(expected_recent)
    ratio = m["contraction_ratio"]
    assert signal(fixture, base_min=30, max_atr_ratio=ratio)
    assert signal(fixture, base_min=30, max_atr_ratio=ratio-1e-5) is None


def test_volume_contraction_strict_boundary(fixture):
    assert signal(fixture).metadata["volume_contraction_ratio"] == 0.5
    assert signal(fixture, max_volume_ratio=0.5) is None
    fixture.loc[255:259,"volume"] = 1_000_000
    assert signal(fixture) is None


def test_breakout_volume_prior_average_excludes_breakout(fixture):
    expected = (15*1_000_000+5*500_000)/20
    assert signal(fixture).metadata["prior_average_volume"] == expected
    fixture.loc[260,"volume"] = expected
    assert signal(fixture) is None
    fixture.loc[260,"volume"] = expected+1
    assert signal(fixture)


def test_breakout_unavailable_until_daily_bucket_complete(fixture):
    ctx = context(fixture, decision_time=(fixture.available_at.iloc[260]-pd.Timedelta(microseconds=1)).to_pydatetime())
    assert len(ctx.bars()) == 260
    assert Momentum().on_bar(ctx) is None
    assert signal(fixture)


@pytest.mark.parametrize("opening,reason", [(102.0001,"entry_too_extended"),(100,"open_not_above_pivot"),(99,"open_not_above_pivot")])
def test_chase_and_gap_rejections_keep_setup(fixture, opening, reason):
    fixture.loc[261,"open"] = opening
    r = run(fixture)
    assert not r["trades"]
    setup = r["setups"][0]
    assert setup["status"] == "rejected"
    assert setup["outcome"]["breakout_confirmed"] and not setup["outcome"]["entered"]
    assert setup["outcome"]["next_open"] == opening
    assert setup["outcome"]["rejection_reason"] == reason


def test_chase_upper_boundary_is_inclusive(fixture):
    fixture.loc[261,"open"] = 102
    assert run(fixture)["setups"][0]["status"] == "filled"


def test_structural_stop_confirmation_excludes_breakout_and_future(fixture):
    base = fixture.iloc[230:260]
    assert confirmed_swing_low(base).low == 97.5
    assert confirmed_swing_low(base).timestamp == fixture.timestamp.iloc[257]
    # New low at final base bar cannot be confirmed by N or N+1.
    fixture.loc[259,"low"] = 97
    assert confirmed_swing_low(fixture.iloc[230:260]) is None
    assert signal(fixture).rejection_reason == "missing_structural_stop"
    assert run(fixture)["setups"][0]["status"] == "rejected"


def test_stop_cap_no_replacement(fixture):
    r = run(fixture, params={"max_stop_distance_pct": 3})
    assert r["setups"][0]["resolution_reason"] == "stop_distance_exceeded"
    assert r["setups"][0]["stop_loss"] == 97.5
    assert not r["trades"]
    assert r["setups"][0]["outcome"]["risk_per_share"] == 3.5
    assert r["setups"][0]["outcome"]["stop_distance_pct"] == 350/101


def test_fill_relative_two_r_uses_engine_costs_and_risk(fixture):
    r = run(fixture, config=BacktestConfig(slippage_bps=10,commission_per_order=1))
    t = r["trades"][0]
    assert t["entry_price"] == pytest.approx(101.101)
    assert t["take_profit"] == t["entry_price"]+2*(t["entry_price"]-97.5)
    assert t["quantity"] == pytest.approx(100/(t["entry_price"]-97.5))
    assert t["r_multiple"] < 2  # Existing commissions, no strategy-specific accounting.


def test_setup_without_next_bar_stays_unfilled(fixture):
    r = run(fixture.iloc[:261])
    assert not r["trades"]
    assert r["setups"][0]["resolution_reason"] == "end_of_data"


def test_future_bars_cannot_change_setup_or_next_open_decision(fixture):
    expected = signal(fixture)
    fixture.loc[261:, ["high","close","volume"]] = 1e9
    assert signal(fixture) == expected
    assert run(fixture)["setups"][0]["fill_price"] == 101
    assert signal(fixture.iloc[:261]) == expected


def test_daily_normalization_dst_and_partial_bucket():
    frame = pd.DataFrame([dict(timestamp=d,open=10,high=11,low=9,close=10,volume=100)
                          for d in ["2024-03-08T05:00:00Z","2024-03-11T04:00:00Z"]])
    full = completed_daily_frame(frame,pd.Timestamp("2024-03-12T04:00:00Z"))
    assert full.timestamp.astype(str).tolist() == ["2024-03-08 14:30:00+00:00","2024-03-11 13:30:00+00:00"]
    partial = completed_daily_frame(frame,pd.Timestamp("2024-03-11T21:00:00Z"))
    assert len(partial) == 1


def test_portfolio_reuses_limits_and_alphabetical_order(fixture):
    r = run(fixture, symbols=("ZZZ","AAA"), config=BacktestConfig(max_open_positions=1))
    assert [t["symbol"] for t in r["trades"]] == ["AAA"]
    assert next(s for s in r["setups"] if s["symbol"] == "ZZZ")["resolution_reason"] == "max_open_positions"
    assert BIAS_WARNING in r["data"]["warnings"]


@pytest.mark.parametrize("params", [{"base_min":31},{"max_atr_ratio":1},{"swing_right":0},{"ema_fast":50},{"target_r":3},{"max_chase_pct":float("nan")}])
def test_invalid_parameters_rejected(params):
    with pytest.raises(ValueError):
        Momentum(**params)


class FakeMarket:
    def __init__(self, frame):
        self.frame = frame
    def get_bars(self, *args, **kwargs):
        return self.frame.copy()


def test_service_contract_and_saved_diagnostics(fixture, monkeypatch):
    service = BacktestService(FakeMarket(fixture))
    monkeypatch.setattr(service,"_load_timeframe", lambda *args: fixture.copy())
    payload = dict(strategy_key=KEY,symbols=["TEST"],start_date="2022-01-01",end_date="2024-01-10",save_run=False)
    r = service.run(payload)
    assert len(r["trades"]) == 1
    assert r["strategy"]["params"] == DEFAULTS
    assert BIAS_WARNING in r["data"]["warnings"]
    for changes in ({"primary_timeframe":"1m"},{"symbols":["XAUUSD"]},{"allow_overnight":False},{"session":"extended"}):
        with pytest.raises(ValueError,match="Momentum baseline requires"):
            service.run({**payload, **changes})


def test_saved_run_roundtrip_preserves_defaults_rejected_setups_and_warning(fixture, monkeypatch, tmp_path):
    database = Database(tmp_path / "saved.db")
    database.initialize()
    service = BacktestService(FakeMarket(fixture), BacktestRunRepository(database))
    fixture.loc[261,"open"] = 103
    fixture.loc[261,"high"] = 103
    monkeypatch.setattr(service,"_load_timeframe", lambda *args: fixture.copy())
    r = service.run(dict(strategy_key=KEY,symbols=["TEST"],start_date="2022-01-01",end_date="2024-01-10"))
    saved = service.get_run(r["saved_run"]["id"])
    assert saved["config"]["strategy_params"] == DEFAULTS
    assert saved["result"]["setups"][0]["outcome"]["rejection_reason"] == "entry_too_extended"
    assert BIAS_WARNING in saved["result"]["data"]["warnings"]


def test_momentum_and_near_high_thresholds(fixture):
    s = signal(fixture)
    assert signal(fixture, min_return_pct=s.metadata["return_pct"]) is None
    fixture.loc[210,"high"] = 120
    assert signal(fixture) is None
    assert signal(fixture,max_distance_high_pct=20)


def test_position_already_open_is_still_a_detected_setup(fixture):
    ctx = context(fixture)
    ctx.position = object()
    assert Momentum().on_bar(ctx).rejection_reason == "position_already_open"


def test_stop_distance_exact_boundary_and_same_bar_policy(fixture):
    assert run(fixture,params={"max_stop_distance_pct":350/101})["trades"]
    fixture.loc[261,"high"] = 109
    fixture.loc[261,"low"] = 97
    assert run(fixture)["trades"][0]["r_multiple"] == -1
    assert run(fixture,config=BacktestConfig(same_bar_policy="target_first"))["trades"][0]["r_multiple"] == 2


def test_fill_filters_apply_on_monday_open_not_friday_overnight_decision(fixture):
    config = BacktestConfig(entry_windows=(("09:30","10:00"),),trading_weekdays=(0,))
    assert run(fixture,config=config)["trades"][0]["entry_price"] == 101
    config = BacktestConfig(entry_windows=(("10:00","11:00"),))
    assert run(fixture,config=config)["setups"][0]["resolution_reason"] == "outside_entry_window"


@pytest.mark.parametrize("bad", ["duplicate","nan","negative","bad_range"])
def test_invalid_daily_data_is_not_silently_used(fixture, bad):
    if bad == "duplicate":
        fixture = pd.concat([fixture,fixture.iloc[:1]])
    elif bad == "nan":
        fixture.loc[0,"volume"] = float("nan")
    elif bad == "negative":
        fixture.loc[0,"volume"] = -1
    else:
        fixture.loc[0,"high"] = 1
    with pytest.raises(ValueError,match="Daily equity data"):
        completed_daily_frame(fixture,pd.Timestamp("2025-01-01",tz="UTC"))
