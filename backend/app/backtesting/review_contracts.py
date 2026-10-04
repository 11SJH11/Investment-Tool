"""Declarative compatibility profiles for strategies predating review_config.

New plugins should declare StrategySpec.review_config. Frontend code never
branches on a Python strategy class or key. Profiles do not change decisions.
"""
from copy import deepcopy
import pandas as pd
import math

LEGACY = {
    "vwap_trend_entry_exit_distance_research_v4": {
        "version": 1,
        "series": [{"id": "vwap", "label": "Session VWAP", "indicator": "rth_vwap_bands", "timeframe": "1m", "params": {"line": "vwap"}, "session_reset": True,
                    "distance_bps_param": "max_entry_vwap_distance_bps"},
                   {"id":"htf_ema","label":"Completed RTH regime EMA","indicator":"rth_trend_ema","timeframe":"1m","params":{"timeframe":{"parameter":"trend_timeframe"},"length":{"parameter":"trend_ema_length"}},"extended_history":True,"history_days":{"parameter":"trend_timeframe","values":{"off":0,"1h":30,"4h":75,"1d":75,"1w":250}}}],
        "confirmation": {"series": "vwap", "entry_param": "entry_confirmation_bars", "exit_param": "exit_confirmation_bars", "exit_reason": "vwap_confirmed_reverse"},
        "record_attributes": {"confirmation_observed": "_streak_count"},
        "entry_fields": ["vwap", "confirmation_bars", "confirmation_count", "trend_timeframe", "trend_ema_length", "htf_close", "htf_ema", "htf_trend_state", "htf_filter_passed"],
    }
}

def review_contract(spec):
    return deepcopy(spec.review_config or LEGACY.get(spec.key, {}))


def record_decision(strategy, ctx):
    config=review_contract(strategy.spec)
    if not config:
        return None
    row=ctx.current_bar
    result={"signal_time":ctx.decision_time.isoformat(),"bar_time":str(row["timestamp"]),"signal_close":float(row["close"])}
    for label,attribute in config.get("record_attributes",{}).items():
        value=getattr(strategy,attribute,None)
        if value is None or isinstance(value,(str,int,float,bool)):
            result[label]=value
    confirmation=config.get("confirmation",{})
    required=max(int(strategy.params.get(confirmation.get("entry_param"),1)),int(strategy.params.get(confirmation.get("exit_param"),1)))
    result["preceding_bars"]=[str(v) for v in ctx.bars(count=min(required,1000))["timestamp"]]
    result["parameters"] = dict(strategy.params)
    # Only declared causal canonical indicators; bounded signal-time work.
    from app.indicators import indicator_registry
    for item in config.get("series",[]):
        tf=item.get("timeframe",ctx.primary_timeframe)
        if not item.get("session_reset"):
            continue
        try:
            bars=ctx.bars(tf,count=500)
            first=pd.Timestamp(bars.iloc[0]["timestamp"]).tz_convert("America/New_York")
            current=pd.Timestamp(row["timestamp"]).tz_convert("America/New_York")
            if first.date()==current.date() and first.hour*60+first.minute>570:
                continue
            indicator=indicator_registry.create(item["indicator"])
            if not indicator.spec.causal:continue
            value=float(indicator.calculate(bars,**item.get("params",{})).iloc[-1])
            if math.isfinite(value):result.setdefault("indicators",{})[item["id"]]=value
        except (KeyError,ValueError,IndexError,TypeError):
            continue
    return result
