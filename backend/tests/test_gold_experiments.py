from dataclasses import replace

import pandas as pd
import pytest

from app.backtesting.context import StrategyContext
from app.backtesting.engine import BacktestEngine
from app.backtesting.models import BacktestConfig, EntrySignal
from app.backtesting.strategies import strategy_registry
from app.backtesting.strategies.gold_experiments import (
    KEYS, PREFIX, REFERENCE, VARIANTS, dxy_alignment, evaluate_filters,
)
from app.backtesting.strategies.xau_liquidity_type3 import XauLiquiditySweepType3Baseline
from app.services.backtest import BacktestService


def bars(n=40, start="2026-01-05T09:00Z", freq="min"):
    return pd.DataFrame(dict(timestamp=pd.date_range(start,periods=n,freq=freq),
        open=[100.]*n, high=[101.]*n, low=[99.]*n, close=[100.]*n, volume=[10.]*n))


def fixture():
    one = bars(34)
    one.loc[15,"high"] = 106
    one.loc[30,"low"] = 94
    one.loc[31,["open","high","low","close"]] = [100,108,100,107]
    one.loc[32,["open","high","low","close"]] = [102,104,100,103]
    one.loc[33,["open","high","low","close"]] = [103,112,102,111]
    hourly = bars(25,"2026-01-03T00:00Z","h")
    hourly["open"] = hourly["close"] = [100.+i for i in range(25)]
    hourly["high"] = hourly.close+1
    hourly["low"] = hourly.close-1
    hourly.loc[2,"low"] = 95
    return {"1m":one,"1h":hourly}


def run(strategy, frames=None):
    return BacktestEngine(BacktestConfig(sizing_mode="quantity",risk_value=1)).run(
        symbol_frames={"XAUUSD":frames or fixture()},strategies={"XAUUSD":strategy},primary_timeframe="1m")


def signal(one, long=True, sweep_index=20, entry=100):
    return EntrySignal("long" if long else "short", 94 if long else 106,
        entry_price=entry, order_type="limit", metadata={
            "sweep_time":one.iloc[sweep_index].timestamp.isoformat(),"sweep_size":.5})


def check(key, one=None, hourly=None, long=True, **kwargs):
    one = bars() if one is None else one
    hourly = bars(25,"2026-01-03","h") if hourly is None else hourly
    return evaluate_filters(signal(one,long,**kwargs),one,hourly,
        one.iloc[-1].timestamp+pd.Timedelta(minutes=1),(key,))[key]


def test_reference_matches_frozen_baseline_hand_worked_trade_exactly():
    baseline = run(XauLiquiditySweepType3Baseline())
    experiment = run(strategy_registry.create(REFERENCE))
    b, = baseline["trades"]
    e, = experiment["trades"]
    assert (b["entry_price"],b["stop_loss"],b["take_profit"],b["exit_price"],b["r_multiple"]) == (101,94,111.5,111.5,1.5)
    assert {k:v for k,v in b.items() if k != "metadata"} == {k:v for k,v in e.items() if k != "metadata"}
    assert baseline["metrics"] == experiment["metrics"]
    assert len(baseline["setups"]) == len(experiment["setups"]) == 1
    assert all(e["metadata"][k] == v for k,v in b["metadata"].items())


@pytest.mark.parametrize("name", list(VARIANTS))
def test_registered_variants_keep_baseline_semantics_and_record_filter_decisions(name):
    strategy = strategy_registry.create(PREFIX+name+"_v1")
    assert strategy.params == XauLiquiditySweepType3Baseline().params
    result = run(strategy)
    assert result["setups"]
    setup = result["setups"][0]
    assert (setup["entry_price"],setup["stop_loss"],setup["take_profit"],setup["order_type"]) == (101,94,111.5,"limit")
    assert set(setup["metadata"]["filter_checks"]) == set(VARIANTS[name])
    if "dxy" in VARIANTS[name]:
        assert not result["trades"]
        assert "dxy_data_unavailable" in setup["resolution_reason"]


def test_experiment_parameters_and_market_are_guarded():
    with pytest.raises(ValueError, match="frozen"):
        strategy_registry.create(REFERENCE,target_r=2)
    with pytest.raises(ValueError, match="XAUUSD"):
        BacktestService(object()).run(dict(strategy_key=REFERENCE,symbols=["AAPL"],primary_timeframe="1m"))


@pytest.mark.parametrize("long",[True,False])
def test_compression_boundary_excludes_sweep_and_confirmation(long):
    one=bars(40)
    one.loc[:9,"high"],one.loc[:9,"low"]=105,95
    one.loc[10:19,"high"],one.loc[10:19,"low"]=103.25,96.75
    one.loc[20:,"high"],one.loc[20:,"low"]=1000,1
    assert check("compression",one,long=long)["passed"]
    one.loc[19,"high"]=103.26
    assert not check("compression",one,long=long)["passed"]


def test_missing_minute_and_insufficient_history_fail_closed():
    assert not check("compression",bars(10),sweep_index=5)["passed"]
    one=bars().drop(index=4).reset_index(drop=True)
    assert not check("compression",one,sweep_index=19)["passed"]
    one=bars().drop(index=30).reset_index(drop=True)
    assert not check("overextension",one)["passed"]


@pytest.mark.parametrize("long",[True,False])
def test_displacement_direction_body_and_location(long):
    one=bars()
    one.loc[39,["open","high","low","close"]] = [100,102,100,102] if long else [100,100,98,98]
    assert check("displacement",one,long=long)["passed"]
    assert check("displacement",one,long=long)["prior_atr"] == 2
    one.loc[39,"close"] = 101.99 if long else 98.01
    assert not check("displacement",one,long=long)["passed"]
    one.loc[39,"close"] = 100
    assert not check("displacement",one,long=long)["passed"]


@pytest.mark.parametrize("long",[True,False])
def test_overextension_and_sweep_depth_exact_boundaries(long):
    one=bars()
    one.loc[39,"close"] = 106 if long else 94
    assert check("overextension",one,long=long)["passed"]
    one.loc[39,"close"] += .01 if long else -.01
    assert not check("overextension",one,long=long)["passed"]
    assert check("sweep_depth",one,long=long)["passed"]  # .5 / ATR2 = .25
    s=signal(one,long)
    s=replace(s,metadata={**s.metadata,"sweep_size":.49})
    assert not evaluate_filters(s,one,bars(),one.iloc[-1].timestamp,("sweep_depth",))["sweep_depth"]["passed"]


@pytest.mark.parametrize("long",[True,False])
def test_strict_fvg_overlap_invalidation_and_gap_causality(long):
    one=bars(24)
    one.loc[20,["high","low"]] = [100,98]
    one.loc[21,["high","low"]] = [103,99]
    one.loc[22:23,["high","low"]] = [104,102]
    if not long:
        one[["high","low"]] = 200-one[["low","high"]].to_numpy()
    entry=101 if long else 99
    assert check("fvg",one,long=long,entry=entry)["passed"]
    assert not check("fvg",one,long=long,entry=110)["passed"]
    one.loc[23,"low" if long else "high"]=100
    assert not check("fvg",one,long=long,entry=entry)["passed"]


@pytest.mark.parametrize("stamp,expected",[("2026-01-05T08:00Z",True),("2026-01-05T12:00Z",False),
    ("2026-01-05T13:00Z",True),("2026-01-05T17:00Z",False),("2026-07-06T07:00Z",True)])
def test_session_boundaries_and_dst(stamp,expected):
    one=bars(start=pd.Timestamp(stamp)-pd.Timedelta(minutes=39))
    assert check("session",one)["passed"] == expected


def test_htf_and_dxy_alignment_require_history_direction_and_causal_availability():
    h=bars(25,"2026-01-05T00:00Z","h")
    h.close=range(125,100,-1)
    decision=h.iloc[-1].timestamp+pd.Timedelta(hours=1)
    assert dxy_alignment(h,decision,True)["passed"]
    assert not dxy_alignment(h,decision,False)["passed"]
    assert not dxy_alignment(h.iloc[:20],decision,True)["passed"]
    assert not dxy_alignment(h,decision+pd.Timedelta(hours=3),True)["passed"]
    assert not dxy_alignment(h.drop(index=23),decision,True)["passed"]
    future=bars(1,decision,"h");future.close=99999
    assert dxy_alignment(pd.concat([h,future],ignore_index=True),decision,True) == dxy_alignment(h,decision,True)
    assert check("htf",hourly=h,long=False)["passed"]
    assert not check("htf",hourly=h,long=True)["passed"]


@pytest.mark.parametrize("name",list(VARIANTS))
def test_every_variant_prefix_equivalence_under_future_mutation(name):
    frames=fixture()
    prefix={"1m":frames["1m"].iloc[:32],"1h":frames["1h"]}
    altered={k:v.copy() for k,v in frames.items()}
    altered["1m"].loc[32:,["open","high","low","close","volume"]]=1e6
    def decisions(fs):
        strategy=strategy_registry.create(PREFIX+name+"_v1")
        result=[]
        for stamp in prefix["1m"].timestamp:
            s=strategy.on_bar(StrategyContext(symbol="XAUUSD",primary_timeframe="1m",
                decision_time=(stamp+pd.Timedelta(minutes=1)).to_pydatetime(),frames=fs,position=None,equity=10000))
            if s: result.append(s)
        return result
    assert decisions(prefix) == decisions(altered)


def test_service_fingerprints_reference_and_variant_inputs_and_preserves_baseline(tmp_path):
    from app.storage.database import Database
    from app.storage.backtest_run_repository import BacktestRunRepository
    db=Database(tmp_path/"runs.db");db.initialize()
    service=BacktestService(object(),BacktestRunRepository(db))
    frames=fixture()
    service._load_timeframe=lambda symbol,tf,*args:frames[tf].copy()
    payload=dict(symbols=["XAUUSD"],primary_timeframe="1m",start_date="2026-01-05",end_date="2026-01-05")
    base=service.run({**payload,"strategy_key":"xau_liquidity_type3_baseline_v1"})
    ref=service.run({**payload,"strategy_key":REFERENCE})
    filtered=service.run({**payload,"strategy_key":PREFIX+"dxy_v1"})
    assert base["data"]["comparison_signature"] == ref["data"]["comparison_signature"] == filtered["data"]["comparison_signature"]
    assert base["trades"][0]["metadata"]["mfe_r"] == ref["trades"][0]["metadata"]["mfe_r"]
    assert any("DXY data unavailable" in w for w in filtered["data"]["warnings"])
    cost=service.run({**payload,"strategy_key":REFERENCE,"commission_per_order":1})
    assert cost["data"]["comparison_signature"] != ref["data"]["comparison_signature"]
    assert service.get_run(ref["saved_run"]["id"])["result"]["strategy"]["params"]["target_r"] == 1.5
