from copy import deepcopy
import pandas as pd
import pytest
from app.backtesting.excursion_reporting import excursion_diagnostics, THRESHOLDS
from app.backtesting.intraday_reporting import annotate_intraday


def fixture(direction="long"):
    trade = dict(symbol="TEST", direction=direction, entry_price=100., stop_loss=99. if direction=="long" else 101.,
                 take_profit=103., exit_price=99. if direction=="long" else 101.,
                 entry_time="2026-01-05T14:30:00+00:00", exit_time="2026-01-05T14:34:00+00:00",
                 r_multiple=-1., exit_reason="stop_loss", metadata={})
    highs=[100.25,100.5,101.5,102.,999.,9999.]
    lows=[99.9,99.8,99.7,99.6,1.,0.]
    if direction=="short": highs,lows=[200-v for v in lows],[200-v for v in highs]
    bars=pd.DataFrame(dict(timestamp=pd.date_range(trade["entry_time"],periods=6,freq="min"),high=highs,low=lows))
    return trade,bars


@pytest.mark.parametrize("direction",["long","short"])
def test_mirrored_excursions_and_confirmation_times(direction):
    trade,bars=fixture(direction)
    result=excursion_diagnostics(trade,bars,entry_at_open=True)
    assert result["mfe_r"]==2
    assert result["mae_r"]==1
    assert result["mfe_price"]==(102 if direction=="long" else 98)
    assert result["mae_price"]==trade["exit_price"]
    assert result["mfe_time"]==trade["exit_time"]
    assert result["mae_time"]==trade["exit_time"]
    assert result["time_to_mfe_minutes"]==4
    assert result["time_to_mae_minutes"]==4
    assert [result[f"time_to_{k}r"] for k in THRESHOLDS]==[1,2,3,3,4,None]


def test_exit_and_future_extremes_excluded_and_input_unchanged():
    trade,bars=fixture();before=deepcopy(trade)
    expected=excursion_diagnostics(trade,bars,True)
    bars.loc[4:,"high"]=1e10;bars.loc[4:,"low"]=-1e10
    assert excursion_diagnostics(trade,bars,True)==expected
    assert trade==before


def test_unknown_or_limit_fill_excludes_entry_bar_extremes():
    trade,bars=fixture();bars.loc[0,"high"]=500
    assert excursion_diagnostics(trade,bars)["mfe_r"]==2
    assert excursion_diagnostics(trade,bars,True)["mfe_r"]==400


@pytest.mark.parametrize("stop",[100,None,"invalid",float("nan"),float("inf")])
def test_invalid_risk_is_unavailable_in_annotation(stop):
    trade,bars=fixture();trade["stop_loss"]=stop
    result={"trades":[trade],"setups":[]}
    annotate_intraday(result,{"TEST":{"1m":bars}})
    for key in ["mfe_r","mae_r","mfe_price","mae_time","time_to_1r"]:
        assert trade["metadata"][key] is None


def test_missing_bars_only_exact_fills_are_known():
    trade,_=fixture();trade["exit_price"]=101
    result=excursion_diagnostics(trade,None)
    assert result["mfe_r"]==1
    assert result["time_to_1r"]==4
    assert result["time_to_1_5r"] is None
    assert result["mae_time"]==trade["entry_time"]


def test_partial_bar_not_used_and_exact_exit_is_known():
    trade,bars=fixture();trade["exit_time"]="2026-01-05T14:31:30+00:00"
    bars.loc[1,"high"]=500
    result=excursion_diagnostics(trade,bars,True)
    assert result["mfe_r"]==.25
    assert result["time_to_0_5r"] is None
    assert result["time_to_mae_minutes"]==1.5


def test_annotation_preserves_execution_results():
    trade,bars=fixture();facts={k:v for k,v in trade.items() if k!='metadata'}
    result={"trades":[trade],"setups":[]}
    annotate_intraday(result,{"TEST":{"1m":bars}})
    assert {k:v for k,v in trade.items() if k!='metadata'}==facts
