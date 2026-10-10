"""
Ledger research strategy: Turtle / Donchian breakout.

Independent implementation based on the classic 20-bar entry / 10-bar exit
Donchian concept with a 20-bar breakout, 10-bar opposite-channel exit and 2 ATR initial stop.

Important:
- This is a research implementation, not copied TradingView Pine source.
- v1 intentionally tests the simple breakout edge first: no pyramiding, no trailing stop,
  and no trend filter by default.
- The common Ledger engine remains responsible for fills, sizing, costs and P&L
"""

import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


_TIMEFRAMES = {
    0: "15m",
    1: "1h",
    2: "4h",
    3: "1d",
}


def _signal_tf(params):
    return _TIMEFRAMES.get(int(params.get("signal_timeframe_code", 0)), "15m")


def _position_side(position):
    for attr in ("direction", "side"):
        value = getattr(position, attr, None)
        if value in ("long", "short"):
            return value
    return None


@strategy_registry.register
class TurtleDonchianResearchV1(Strategy):
    spec = StrategySpec(
        key="turtle_donchian_research_v1",
        name="Turtle / Donchian Breakout · research v1",
        description=(
            "Previous-bar Donchian breakout, optional EMA trend filter, 2 ATR initial "
            "stop and opposite 10-bar Donchian exit. No pyramiding or trailing stop in v1."
        ),
        defaults={
            "signal_timeframe_code": 0,   # screening baseline: 0=15m, 1=1h, 2=4h, 3=1d
            "entry_lookback": 20,
            "exit_lookback": 10,
            "atr_length": 20,
            "atr_stop_multiple": 2.0,
            "ema_filter_length": 0,       # simple screening baseline: off
            "fixed_target_r": 0.0,        # 0 disables fixed target
        },
        timeframes=("15m", "1h", "4h", "1d"),
        parameters=(
            ParameterSpec("signal_timeframe_code", "Signal TF code", "int", 0, 0, 3, 1),
            ParameterSpec("entry_lookback", "Entry Donchian bars", "int", 20, 5, 100, 1),
            ParameterSpec("exit_lookback", "Exit Donchian bars", "int", 10, 2, 60, 1),
            ParameterSpec("atr_length", "ATR length", "int", 20, 5, 100, 1),
            ParameterSpec("atr_stop_multiple", "ATR stop multiple", "float", 2.0, 0.5, 5.0, 0.25),
            ParameterSpec("ema_filter_length", "EMA trend filter (0=off)", "int", 0, 0, 300, 10),
        ),
        research_parameters=(
            ParameterSpec("fixed_target_r", "Fixed target R (0=off)", "float", 0.0, 0.0, 10.0, 0.5),
        ),
        risk_management={
            "Initial stop": "Entry reference +/- ATR * atr_stop_multiple.",
            "Initial target": "None by default; optional fixed R target for research.",
            "Management": "Initial stop remains fixed; completed close through opposite 10-bar Donchian channel exits.",
        },
        source_file="backend/app/backtesting/strategies/turtle_donchian_research_v1.py",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_bar(self, ctx):
        tf = _signal_tf(self.params)
        entry_n = int(self.params["entry_lookback"])
        exit_n = int(self.params["exit_lookback"])
        atr_n = int(self.params["atr_length"])
        ema_n = int(self.params["ema_filter_length"])
        stop_mult = float(self.params["atr_stop_multiple"])
        fixed_target_r = float(self.params.get("fixed_target_r", 0.0))

        needed = max(entry_n, exit_n, atr_n, ema_n if ema_n > 0 else 0) + 5
        bars = ctx.bars(tf, count=needed)
        if bars is None or len(bars) < max(entry_n, exit_n, atr_n) + 1:
            return None

        current = bars.iloc[-1]
        close = float(current["close"])

        atr_series = ctx.indicator("atr", timeframe=tf, length=atr_n)
        if atr_series is None or len(atr_series) == 0 or pd.isna(atr_series.iloc[-1]):
            return None
        atr = float(atr_series.iloc[-1])
        if not (atr > 0):
            return None

        # Position management is deliberately simple in the screening baseline:
        # the engine keeps the original 2 ATR stop active; the strategy exits only
        # on a completed close through the opposite exit channel.
        if ctx.position is not None:
            side = _position_side(ctx.position)
            if side not in ("long", "short"):
                return None
            prior_exit = bars.iloc[-(exit_n + 1):-1]
            if len(prior_exit) < exit_n:
                return None
            if side == "long":
                exit_level = float(prior_exit["low"].min())
                if close < exit_level:
                    return ExitSignal(reason="turtle_10bar_exit_long", metadata={"exit_level": exit_level, "signal_tf": tf})
                return None
            exit_level = float(prior_exit["high"].max())
            if close > exit_level:
                return ExitSignal(reason="turtle_10bar_exit_short", metadata={"exit_level": exit_level, "signal_tf": tf})
            return None

        # ---- entries use only PREVIOUS completed bars for breakout channel ----
        prior_entry = bars.iloc[-(entry_n + 1):-1]
        if len(prior_entry) < entry_n:
            return None

        upper = float(prior_entry["high"].max())
        lower = float(prior_entry["low"].min())

        ema = None 
        if ema_n > 0:
            ema_series = ctx.indicator("ema", timeframe=tf, length=ema_n)
            if ema_series is None or len(ema_series) == 0 or pd.isna(ema_series.iloc[-1]):
                return None
            ema = float(ema_series.iloc[-1])

        long_ok = close > upper and (ema is None or close > ema)
        short_ok = close < lower and (ema is None or close < ema)

        if long_ok and short_ok:
            # Should be impossible on a normal OHLC close, but reject ambiguity.
            return None

        if long_ok:
            stop = close - stop_mult * atr
            target_kwargs = {"target_r": fixed_target_r} if fixed_target_r > 0 else {}
            return EntrySignal(
                "long",
                stop_loss=stop,
                reason="turtle_donchian_long",
                metadata={
                    "signal_tf": tf,
                    "entry_channel_high": upper,
                    "entry_channel_low": lower,
                    "atr": atr,
                    "ema": ema,
                    "entry_lookback": entry_n,
                    "exit_lookback": exit_n,
                    "atr_stop_multiple": stop_mult,
                    "pyramiding_enabled": False,
                    "atr_trailing_enabled": False,
                },
                **target_kwargs,
            )

        if short_ok:
            stop = close + stop_mult * atr
            target_kwargs = {"target_r": fixed_target_r} if fixed_target_r > 0 else {}
            return EntrySignal(
                "short",
                stop_loss=stop,
                reason="turtle_donchian_short",
                metadata={
                    "signal_tf": tf,
                    "entry_channel_high": upper,
                    "entry_channel_low": lower,
                    "atr": atr,
                    "ema": ema,
                    "entry_lookback": entry_n,
                    "exit_lookback": exit_n,
                    "atr_stop_multiple": stop_mult,
                    "pyramiding_enabled": False,
                    "atr_trailing_enabled": False,
                },
                **target_kwargs,
            )

        return None


def test_timeframe_mapping():
    assert _TIMEFRAMES[0] == "15m"
    assert _TIMEFRAMES[1] == "1h"
    assert _TIMEFRAMES[2] == "4h"
    assert _TIMEFRAMES[3] == "1d"
