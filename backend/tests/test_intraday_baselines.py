import pandas as pd
import pytest

from app.backtesting.context import StrategyContext
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig
from app.backtesting.intraday_reporting import annotate_intraday
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.intraday_baselines import (
    ORB, ORB_RESEARCH, VWAP, OpeningRangeBreakout, OpeningRangeResearch,
    VwapMeanReversion, session_bars,
)
from app.indicators.rth_vwap import RthVwapBands, session_moments
from app.services.backtest import BacktestService


def frame(prices, day="2026-01-05", start="09:30"):
    stamps = pd.date_range(f"{day} {start}", periods=len(prices), freq="min", tz="America/New_York").tz_convert("UTC")
    return pd.DataFrame(dict(timestamp=stamps, open=prices, high=prices, low=prices,
                             close=prices, volume=[100]*len(prices)))


def context(bars, index=None, symbol="AAPL", decision=None, timeframe="1m"):
    index = len(bars)-1 if index is None else index
    return StrategyContext(symbol=symbol, primary_timeframe=timeframe,
        decision_time=decision or (bars.iloc[index].timestamp+pd.Timedelta(minutes=1)).to_pydatetime(),
        frames={timeframe: bars}, position=None, equity=1_000_000)


def orb_frame(day="2026-01-05"):
    bars = frame([100]*15+[102, 103, 111], day)
    bars.loc[:14, "high"] = 101
    bars.loc[:14, "low"] = 99
    return bars


def simulate(strategy, bars, symbol="AAPL", **params):
    config = BacktestConfig(**dict(starting_balance=1_000_000, sizing_mode="quantity", risk_value=1, **params))
    return BacktestEngine(config).run(symbol_frames={symbol:{"1m":bars}},
        strategies={symbol:strategy}, primary_timeframe="1m")


def signals(strategy, bars, symbol="AAPL"):
    return [s for i in range(len(bars)) if (s := strategy.on_bar(context(bars, i, symbol)))]


def test_registry_and_frozen_parameters():
    assert {ORB, ORB_RESEARCH, VWAP} <= {s.key for s in strategy_registry.specs()}
    with pytest.raises(ValueError, match="frozen"):
        OpeningRangeBreakout(target_r=3)
    with pytest.raises(ValueError, match="frozen"):
        VwapMeanReversion(deviations=3)


@pytest.mark.parametrize("params", [{"range_minutes":10}, {"target_r":0}, {"target_r":float("nan")},
    {"trend_ema_length":2.5}, {"entry_mode":"unknown"}, {"volume_ratio":-1}, {"unknown":1}])
def test_research_parameter_validation(params):
    with pytest.raises(ValueError):
        OpeningRangeResearch(**params)


@pytest.mark.parametrize("symbol,timeframe", [("XAUUSD","1m"), ("NQ1!","1m"), ("AAPL","5m")])
def test_market_rejections(symbol, timeframe):
    with pytest.raises(ValueError):
        OpeningRangeBreakout().on_bar(context(orb_frame(), symbol=symbol, timeframe=timeframe))


def test_service_rejects_wrong_market_before_fetch():
    class NoFetch:
        def fetch(self, *args, **kwargs):
            pytest.fail("Invalid strategy request reached provider")
    with pytest.raises(ValueError, match="one-minute"):
        BacktestService(NoFetch()).run(dict(strategy_key=VWAP, symbols=["XAUUSD"], primary_timeframe="1m"))


def test_orb_hand_worked_next_open_and_actual_fill_2r():
    bars = orb_frame()
    result = simulate(OpeningRangeBreakout(), bars)
    trade, = result["trades"]
    assert trade["entry_time"] == bars.iloc[16].timestamp.isoformat()
    assert trade["entry_price"] == 103
    assert trade["stop_loss"] == 99 and trade["take_profit"] == 111
    assert trade["exit_price"] == 111 and trade["r_multiple"] == 2
    assert trade["metadata"]["or_high"] == 101
    assert trade["metadata"]["range_minutes"] == 15
    assert result["setups"][0]["detected_at"] == bars.iloc[16].timestamp.isoformat()


def test_orb_short_mirror():
    bars = orb_frame()
    for key in ("open", "high", "low", "close"):
        bars[key] = 200-bars[key]
    bars[["high", "low"]] = bars[["low", "high"]].to_numpy()
    trade, = simulate(OpeningRangeBreakout(), bars)["trades"]
    assert (trade["entry_price"], trade["stop_loss"], trade["take_profit"], trade["r_multiple"]) == (97,101,89,2)


def test_orb_only_completed_close_and_frozen_prebreakout_range():
    bars = orb_frame()
    strategy = OpeningRangeBreakout()
    assert strategy.on_bar(context(bars, 14)) is None
    assert strategy.on_bar(context(bars, decision=(bars.iloc[15].timestamp+pd.Timedelta(seconds=59)).to_pydatetime())) is None
    bars.loc[15,"high"] = 500  # Current wick cannot redefine the range.
    signal = strategy.on_bar(context(bars, 15))
    assert signal.metadata["or_high"] == 101 and signal.stop_loss == 99


def test_wicks_and_equal_close_do_not_confirm_baseline():
    bars = orb_frame().iloc[:16].copy()
    bars.loc[15,["open","close","high","low"]] = [101,101,110,99]
    assert not signals(OpeningRangeBreakout(), bars)
    assert len(signals(OpeningRangeResearch(confirmation="wick"), bars)) == 1
    bars.loc[15,"low"] = 90
    assert signals(OpeningRangeResearch(confirmation="wick"), bars)[0].rejection_reason == "ambiguous_wick_breakout"


@pytest.mark.parametrize("day,utc_hour", [("2026-01-05",14), ("2026-07-06",13)])
def test_session_anchor_dst_premarket_and_missing_minutes(day, utc_hour):
    bars = orb_frame(day)
    pre = frame([1000], day, "09:29")
    combined = pd.concat([pre,bars],ignore_index=True)
    signal = signals(OpeningRangeBreakout(),combined)[0]
    assert pd.Timestamp(signal.metadata["range_start"]).hour == utc_hour
    assert signal.metadata["or_high"] == 101
    assert not signals(OpeningRangeBreakout(),bars.drop(index=3).reset_index(drop=True))


def test_one_attempt_per_direction_and_session_reset():
    bars = orb_frame()
    assert len(signals(OpeningRangeBreakout(), bars)) == 1
    both = pd.concat([bars, orb_frame("2026-01-06")],ignore_index=True)
    assert len(signals(OpeningRangeBreakout(), both)) == 2
    bars.loc[17,["open","high","low","close"]] = 98
    assert [s.direction for s in signals(OpeningRangeBreakout(),bars)] == ["long","short"]


@pytest.mark.parametrize("minutes", [5,15,30])
def test_research_range_boundaries(minutes):
    bars = frame([100]*minutes+[102])
    bars.loc[:minutes-1,"high"] = 101
    bars.loc[:minutes-1,"low"] = 99
    signals_ = signals(OpeningRangeResearch(range_minutes=str(minutes)),bars)
    assert len(signals_) == 1 and signals_[0].metadata["range_minutes"] == minutes


@pytest.mark.parametrize("params,reason", [({"volume_ratio":1},"volume_filter"),
    ({"min_range_atr":2},"range_atr_filter"), ({"trend_ema_length":50},"trend_filter")])
def test_research_filters_record_rejected_setups(params,reason):
    result = simulate(OpeningRangeResearch(**params),orb_frame())
    assert not result["trades"]
    assert result["setups"][0]["resolution_reason"] == reason


def test_research_volume_excludes_breakout_and_retest_limit():
    bars = frame([100]*20+[102,101,105])
    bars.loc[:19,"high"] = 101
    bars.loc[:19,"low"] = 99
    bars.loc[20,"volume"] = 200
    signal = signals(OpeningRangeResearch(volume_ratio=2),bars)[0]
    assert not signal.rejection_reason and signal.metadata["breakout_volume_ratio"] == 2
    trade, = simulate(OpeningRangeResearch(entry_mode="retest"),bars)["trades"]
    assert trade["entry_price"] == 101 and trade["take_profit"] == 105


def test_entry_expires_before_next_session_market_or_limit():
    first = orb_frame().iloc[:16]
    second = frame([103], "2026-01-06")
    bars = pd.concat([first,second],ignore_index=True)
    for strategy in (OpeningRangeBreakout(),OpeningRangeResearch(entry_mode="retest")):
        result = simulate(strategy,bars)
        assert not result["trades"]
        assert result["setups"][0]["resolution_reason"] == "entry_expired"


@pytest.mark.parametrize("policy,expected", [("stop_first",-1),("target_first",2)])
def test_common_same_bar_policy_preserved(policy,expected):
    bars = orb_frame().iloc[:17].copy()
    bars.loc[16,["low","high"]] = [98,112]
    trade, = simulate(OpeningRangeBreakout(),bars,same_bar_policy=policy)["trades"]
    assert trade["r_multiple"] == expected


def test_futures_use_existing_contract_economics():
    trade, = simulate(OpeningRangeBreakout(),orb_frame(),symbol="NQZ6")["trades"]
    assert trade["quantity"] == 1 and trade["gross_pnl"] == 160 and trade["r_multiple"] == 2


def test_weighted_population_formula_zero_volume_reset_and_indicator_lines():
    bars = frame([100,102,999])
    bars.volume = [1,3,0]
    values = session_moments(bars)
    assert values.iloc[-1].vwap == 101.5
    assert values.iloc[-1].sd == pytest.approx(.75**.5)
    for line, expected in (("vwap",101.5),("sd",.75**.5),("upper",101.5+2*.75**.5),("lower",101.5-2*.75**.5)):
        assert RthVwapBands().calculate(bars,line=line).iloc[-1] == pytest.approx(expected)
    multi = pd.concat([frame([999],start="09:29"),bars,frame([50],"2026-01-06")],ignore_index=True)
    assert pd.isna(session_moments(multi).iloc[0].vwap)
    assert session_moments(multi).iloc[-1].vwap == 50
    bars.loc[0,"volume"] = -1
    with pytest.raises(ValueError):
        session_moments(bars)


def vwap_frame():
    bars = frame([100]*20+[90,96,96,100])
    bars.loc[23,["open","low"]] = 96  # Touch target intrabar, without a favorable opening gap.
    return bars


def test_vwap_hand_worked_excursion_reentry_next_fill_frozen_target():
    bars = vwap_frame()
    result = simulate(VwapMeanReversion(),bars)
    trade, = result["trades"]
    target = 2186/22
    assert trade["entry_time"] == bars.iloc[22].timestamp.isoformat()
    assert trade["entry_price"] == 96 and trade["stop_loss"] == 90
    assert trade["take_profit"] == pytest.approx(target)
    assert trade["exit_price"] == pytest.approx(target)
    assert trade["r_multiple"] == pytest.approx((target-96)/6)
    assert trade["metadata"]["excursion_start"] == bars.iloc[20].timestamp.isoformat()
    assert trade["metadata"]["confirmed_at"] == bars.iloc[22].timestamp.isoformat()


def test_vwap_short_mirror_and_futures_target_tick():
    bars = vwap_frame()
    bars[["open","high","low","close"]] = 200-bars[["open","high","low","close"]]
    bars[["high","low"]] = bars[["low","high"]].to_numpy()
    trade, = simulate(VwapMeanReversion(),bars)["trades"]
    assert trade["direction"] == "short" and trade["stop_loss"] == 110
    assert trade["take_profit"] == pytest.approx(200-2186/22)
    trade, = simulate(VwapMeanReversion(),vwap_frame(),symbol="NQZ6")["trades"]
    assert trade["take_profit"] == 99.25


def test_vwap_wick_alone_does_not_arm_and_incomplete_bar_not_seen():
    bars = vwap_frame()
    bars.loc[20,["open","close","high"]] = 100
    strategy = VwapMeanReversion()
    assert not signals(strategy,bars.iloc[:21])
    assert strategy.armed is None
    strategy = VwapMeanReversion()
    original = vwap_frame()
    strategy.on_bar(context(original,20))
    assert strategy.on_bar(context(original,decision=(original.iloc[21].timestamp+pd.Timedelta(seconds=59)).to_pydatetime())) is None
    assert strategy.on_bar(context(original,21)) is not None


def test_vwap_reset_missing_minutes_and_next_open_gap_rejection():
    bars = vwap_frame()
    assert not signals(VwapMeanReversion(),bars.drop(index=2).reset_index(drop=True))
    strategy = VwapMeanReversion()
    assert not signals(strategy,bars.iloc[:21])
    assert not signals(strategy,frame([96,96],"2026-01-06"))
    bars.loc[22,["open","high","low","close"]] = 105
    result = simulate(VwapMeanReversion(),bars)
    assert not result["trades"] and result["setups"][0]["status"] == "rejected"


def test_vwap_confirmation_already_past_target_is_recorded():
    bars = vwap_frame().iloc[:22].copy()
    bars.loc[21,["open","high","low","close"]] = 100
    result = simulate(VwapMeanReversion(),bars)
    assert result["setups"][0]["resolution_reason"] == "confirmation_already_at_vwap_target"


@pytest.mark.parametrize("factory,make_bars,index", [(OpeningRangeBreakout,orb_frame,15),(VwapMeanReversion,vwap_frame,21)])
def test_future_mutation_and_prefix_equivalence(factory,make_bars,index):
    bars = make_bars()
    expected = signals(factory(),bars.iloc[:index+1])
    changed = bars.copy()
    changed.loc[index+1:,["open","high","low","close","volume"]] = 999999
    strategy = factory()
    actual = [s for i in range(index+1) if (s:=strategy.on_bar(context(changed,i)))]
    assert actual == expected
    pd.testing.assert_series_equal(RthVwapBands().calculate(changed).iloc[:index+1],
                                  RthVwapBands().calculate(bars.iloc[:index+1]))


def test_reporting_outcomes_and_lower_bound_excursions():
    bars = orb_frame()
    bars.loc[17,"high"] = 1000  # Exit-bar extreme must not inflate MFE.
    result = simulate(OpeningRangeBreakout(),bars)
    annotate_intraday(result,{"AAPL":{"1m":bars}})
    meta = result["trades"][0]["metadata"]
    assert meta["mfe_r"] == 2 and meta["mae_r"] == 0
    assert meta["bars_in_trade"] == 1 and meta["minutes_in_trade"] == 1
    assert result["setups"][0]["metadata"]["setup_entered"]
    assert result["setups"][0]["metadata"]["result_r"] == 2
    assert any("survivorship" in x for x in result["data"]["warnings"])


def test_retest_deadline_is_exclusive_even_when_price_touches():
    bars = frame([100]*15+[102]*16+[101])
    bars.loc[:14,"high"] = 101
    bars.loc[:14,"low"] = 99
    result = simulate(OpeningRangeResearch(entry_mode="retest"),bars)
    assert not result["trades"]
    assert result["setups"][0]["resolution_reason"] == "entry_expired"


def test_forced_boundary_retains_detected_setup_without_entry():
    result = simulate(OpeningRangeBreakout(),orb_frame().iloc[:16],allow_overnight=False)
    assert not result["trades"]
    assert result["setups"][0]["resolution_reason"] == "session_boundary"


def test_no_confirmations_at_session_close_and_expiry_at_exact_16():
    bars = frame([100]*388+[102,103,104])
    bars.loc[:14,"high"] = 101
    bars.loc[:14,"low"] = 99
    strategy = OpeningRangeBreakout()
    signal = strategy.on_bar(context(bars,388))
    assert signal.expires_at.hour == 16
    assert OpeningRangeBreakout().on_bar(context(bars,389)) is None
    assert OpeningRangeBreakout().on_bar(context(bars,390)) is None
    # Missing 15:59 leaves the pending 15:59 confirmation until 16:00.
    result = simulate(OpeningRangeBreakout(),bars.drop(index=389).reset_index(drop=True))
    assert not result["trades"]
    assert result["setups"][0]["resolution_reason"] == "entry_expired"


def test_vwap_pending_entry_expires_and_zero_volume_never_arms():
    bars = pd.concat([vwap_frame().iloc[:22],frame([96],"2026-01-06")],ignore_index=True)
    result = simulate(VwapMeanReversion(),bars)
    assert not result["trades"]
    assert result["setups"][0]["resolution_reason"] == "entry_expired"
    bars = vwap_frame()
    bars.volume = 0
    assert not signals(VwapMeanReversion(),bars)


@pytest.mark.parametrize("key", [ORB,ORB_RESEARCH,VWAP])
def test_service_saves_canonical_parameters_and_audit_without_network(tmp_path,key):
    from app.storage.database import Database
    from app.storage.backtest_run_repository import BacktestRunRepository
    database = Database(tmp_path / "runs.sqlite")
    database.initialize()
    service = BacktestService(object(),BacktestRunRepository(database))
    bars = vwap_frame() if key == VWAP else orb_frame()
    service._load_timeframe = lambda *args: bars.copy()
    result = service.run(dict(strategy_key=key,symbols=["AAPL"],primary_timeframe="1m",
        start_date="2026-01-05",end_date="2026-01-05",sizing_mode="quantity",risk_value=1))
    saved = service.get_run(result["saved_run"]["id"])
    assert saved["result"]["trades"][0]["metadata"]["mfe_r"] is not None
    assert saved["result"]["strategy"]["key"] == key
    assert saved["result"]["strategy"]["params"] == strategy_registry.create(key).params
    assert saved["result"]["setups"][0]["metadata"]["setup_entered"]
