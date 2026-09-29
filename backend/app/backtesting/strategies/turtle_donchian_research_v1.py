"""
Ledger research strategy: Turtle / Donchian breakout.

Independent implementation based on the classic 20-bar entry / 10-bar exit
Donchian concept, ATR ("N") risk control and optional long-term EMA filter.

Important:
- This is a research implementation, not copied TradingView Pine source.
- Ledger currently has clean stop/partial management but no dedicated same-position
  pyramid/add-on primitive, so v1 intentionally tests the core breakout edge first.
- The common Ledger engine remains responsible for fills, sizing, costs and P&L.
"""

from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


_TIMEFRAMES = {
    0: "15m",
    1: "1h",
    2: "4h",
    3: "1d",
}


def _signal_tf(params):
    return _TIMEFRAMES.get(int(params.get("signal_timeframe_code", 1)), "1h")


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
            "Previous-bar Donchian breakout, optional EMA trend filter, ATR initial "
            "stop, ATR trailing stop and opposite Donchian exit. No pyramiding in v1."
        ),
        defaults={
            "signal_timeframe_code": 1,   # 0=15m, 1=1h, 2=4h, 3=1d
            "entry_lookback": 20,
            "exit_lookback": 10,
            "atr_length": 20,
            "atr_stop_multiple": 2.0,
            "ema_filter_length": 200,     # 0 disables
            "fixed_target_r": 0.0,        # 0 disables fixed target
        },
        timeframes=("15m", "1h", "4h", "1d"),
        parameters=(
            ParameterSpec("signal_timeframe_code", "Signal TF code", "int", 1, 0, 3, 1),
            ParameterSpec("entry_lookback", "Entry Donchian bars", "int", 20, 5, 100, 1),
            ParameterSpec("exit_lookback", "Exit Donchian bars", "int", 10, 2, 60, 1),
            ParameterSpec("atr_length", "ATR length", "int", 20, 5, 100, 1),
            ParameterSpec("atr_stop_multiple", "ATR stop multiple", "float", 2.0, 0.5, 5.0, 0.25),
            ParameterSpec("ema_filter_length", "EMA trend filter (0=off)", "int", 200, 0, 300, 10),
        ),
        research_parameters=(
            ParameterSpec("fixed_target_r", "Fixed target R (0=off)", "float", 0.0, 0.0, 10.0, 0.5),
        ),
        risk_management={
            "Initial stop": "Entry reference +/- ATR * atr_stop_multiple.",
            "Initial target": "None by default; optional fixed R target for research.",
            "Management": "ATR trailing stop plus opposite Donchian exit.",
        },
        source_file="backend/app/backtesting/strategies/turtle_donchian_research_v1.py",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._active_side = None
        self._favourable_extreme = None
        self._trail_stop = None

    def _reset_position_state(self):
        self._active_side = None
        self._favourable_extreme = None
        self._trail_stop = None

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
        high = float(current["high"])
        low = float(current["low"])

        atr = ctx.indicator("atr", timeframe=tf, length=atr_n)
        if atr is None:
            return None
        atr = float(atr)
        if not (atr > 0):
            return None

        # ---- position management ----
        if ctx.position is not None:
            side = _position_side(ctx.position)
            if side not in ("long", "short"):
                return None

            if self._active_side != side:
                self._active_side = side
                self._favourable_extreme = high if side == "long" else low
                self._trail_stop = None

            prior_exit = bars.iloc[-(exit_n + 1):-1]
            if len(prior_exit) < exit_n:
                return None

            if side == "long":
                exit_level = float(prior_exit["low"].min())
                self._favourable_extreme = max(float(self._favourable_extreme), high)
                candidate_stop = self._favourable_extreme - stop_mult * atr
                self._trail_stop = candidate_stop if self._trail_stop is None else max(self._trail_stop, candidate_stop)

                if close < exit_level:
                    self._reset_position_state()
                    return ExitSignal(
                        reason="turtle_10bar_exit_long",
                        metadata={"exit_level": exit_level, "signal_tf": tf},
                    )
                return ManagePositionSignal(
                    new_stop_loss=float(self._trail_stop),
                    reason="turtle_atr_trail_long",
                    metadata={"atr": atr, "trail_stop": float(self._trail_stop), "signal_tf": tf},
                )

            exit_level = float(prior_exit["high"].max())
            self._favourable_extreme = min(float(self._favourable_extreme), low)
            candidate_stop = self._favourable_extreme + stop_mult * atr
            self._trail_stop = candidate_stop if self._trail_stop is None else min(self._trail_stop, candidate_stop)

            if close > exit_level:
                self._reset_position_state()
                return ExitSignal(
                    reason="turtle_10bar_exit_short",
                    metadata={"exit_level": exit_level, "signal_tf": tf},
                )
            return ManagePositionSignal(
                new_stop_loss=float(self._trail_stop),
                reason="turtle_atr_trail_short",
                metadata={"atr": atr, "trail_stop": float(self._trail_stop), "signal_tf": tf},
            )

        # Flat again after an exit.
        self._reset_position_state()

        # ---- entries use only PREVIOUS completed bars for breakout channel ----
        prior_entry = bars.iloc[-(entry_n + 1):-1]
        if len(prior_entry) < entry_n:
            return None

        upper = float(prior_entry["high"].max())
        lower = float(prior_entry["low"].min())

        ema = None
        if ema_n > 0:
            ema = ctx.indicator("ema", timeframe=tf, length=ema_n)
            if ema is None:
                return None
            ema = float(ema)

        long_ok = close > upper and (ema is None or close > ema)
        short_ok = close < lower and (ema is None or close < ema)

        if long_ok and short_ok:
            # Should be impossible on a normal OHLC close, but reject ambiguity.
            return None

        if long_ok:
            stop = close - stop_mult * atr
            target = None if fixed_target_r <= 0 else close + (close - stop) * fixed_target_r
            return EntrySignal(
                "long",
                stop_loss=stop,
                take_profit=target,
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
                },
            )

        if short_ok:
            stop = close + stop_mult * atr
            target = None if fixed_target_r <= 0 else close - (stop - close) * fixed_target_r
            return EntrySignal(
                "short",
                stop_loss=stop,
                take_profit=target,
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
                },
            )

        return None


def test_timeframe_mapping():
    assert _TIMEFRAMES[0] == "15m"
    assert _TIMEFRAMES[1] == "1h"
    assert _TIMEFRAMES[2] == "4h"
    assert _TIMEFRAMES[3] == "1d"
