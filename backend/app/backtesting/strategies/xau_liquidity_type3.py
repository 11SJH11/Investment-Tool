from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.context import StrategyContext
from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

TOKYO = ZoneInfo("Asia/Tokyo")
LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")


@strategy_registry.register
class XauLiquiditySweepType3Baseline(Strategy):
    """
    Baseline v1.1.

    1H pivots define liquidity.

    After a 1m sweep, Type 3 no longer uses the latest tiny pivot.
    Instead it uses the most recent meaningful opposing swing belonging
    to the leg that led into the sweep.

    Sessions remain labels only.
    """

    spec = StrategySpec(
        key="xau_liquidity_type3_baseline_v1",
        name="XAUUSD Liquidity Sweep + Type 3 + 50% · baseline v1.1",
        description=(
            "1H liquidity sweep followed by a meaningful 1m structural break. "
            "The Type-3 swing is selected from the pre-sweep leg rather than "
            "the nearest micro pivot. Entry waits at the 50% retracement, "
            "stop remains at the sweep structural extreme, target is 1.5R."
        ),
        category="Research baseline",
        defaults={
            "direction": "both",

            # Higher-timeframe liquidity.
            "liquidity_pivot_left": 2,
            "liquidity_pivot_right": 2,

            # Execution swings.
            "execution_pivot_left": 2,
            "execution_pivot_right": 2,

            # New: how far back we search for the meaningful pre-sweep swing.
            "structure_lookback_bars": 40,

            # New: require some separation between the swing and sweep.
            "minimum_structure_bars": 3,

            "max_type3_wait_bars": 120,
            "limit_wait_bars": 120,
            "entry_retrace": 0.5,
            "target_r": 1.5,
        },
        timeframes=("1m", "1h"),
        parameters=(
            ParameterSpec(
                "direction",
                "Direction",
                "choice",
                "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "liquidity_pivot_left",
                "1H pivot left bars",
                "int",
                2,
                1,
                10,
                1,
                help="Mechanical definition of the higher-timeframe liquidity level.",
            ),
            ParameterSpec(
                "liquidity_pivot_right",
                "1H pivot right bars",
                "int",
                2,
                1,
                10,
                1,
            ),
            ParameterSpec(
                "execution_pivot_left",
                "1m swing left bars",
                "int",
                2,
                1,
                10,
                1,
            ),
            ParameterSpec(
                "execution_pivot_right",
                "1m swing right bars",
                "int",
                2,
                1,
                10,
                1,
            ),
            ParameterSpec(
                "structure_lookback_bars",
                "Type 3 structure lookback",
                "int",
                40,
                10,
                180,
                5,
                help=(
                    "How far before the sweep Ledger searches for the meaningful "
                    "opposing 1m swing."
                ),
            ),
            ParameterSpec(
                "minimum_structure_bars",
                "Minimum swing → sweep bars",
                "int",
                3,
                1,
                30,
                1,
                help=(
                    "Prevents a tiny swing immediately beside the sweep from being "
                    "treated as the Type-3 structure."
                ),
            ),
            ParameterSpec(
                "max_type3_wait_bars",
                "Max bars sweep → Type 3",
                "int",
                120,
                1,
                1440,
                1,
            ),
            ParameterSpec(
                "limit_wait_bars",
                "Max bars waiting at 50%",
                "int",
                120,
                1,
                1440,
                1,
            ),
        ),
        research_parameters=(
            ParameterSpec(
                "entry_retrace",
                "Entry retracement",
                "float",
                0.5,
                0.1,
                0.9,
                0.05,
            ),
            ParameterSpec(
                "target_r",
                "Target R",
                "float",
                1.5,
                0.5,
                5.0,
                0.25,
            ),
        ),
        risk_management={
            "Liquidity": "Most recent confirmed 1H pivot high/low",
            "Confirmation": (
                "1m candle CLOSE through meaningful pre-sweep opposing swing"
            ),
            "Entry": "Persistent limit at 50% of confirmation impulse",
            "Stop": "Structural sweep / Type-3 extreme",
            "Target": "1.5R baseline",
            "Session": "Sessions are labels only; no session filtering",
            "Confluences": "None in baseline v1.1",
        },
        source_file="backend/app/backtesting/strategies/xau_liquidity_type3.py",
    )

    def __init__(self, **params):
        super().__init__(**params)
        self._state: dict | None = None

    def reset(self) -> None:
        self._state = None

    def on_bar(self, ctx: StrategyContext):
        if ctx.primary_timeframe != "1m":
            return None

        one = ctx.bars("1m")
        hourly = ctx.bars("1h")

        if len(one) < 12 or len(hourly) < 8 or ctx.position is not None:
            return None

        current = one.iloc[-1]
        current_time = _ts(current["timestamp"])
        direction = str(self.params["direction"])

        # ------------------------------------------------------------
        # Existing sweep waiting for Type-3 confirmation.
        # ------------------------------------------------------------
        if self._state is not None:
            state = self._state
            state["bars_waited"] += 1

            if state["bars_waited"] > int(self.params["max_type3_wait_bars"]):
                self._state = None
                return None

            if state["direction"] == "long":
                # Continue updating the true post-sweep structural low.
                if float(current["low"]) < state["structural_extreme"]:
                    state["structural_extreme"] = float(current["low"])
                    state["structural_time"] = current_time

                break_level = state.get("break_level")

                if (
                    break_level is not None
                    and float(current["close"]) > float(break_level)
                ):
                    return self._confirm(
                        state,
                        current,
                        current_time,
                    )

            else:
                # Continue updating the true post-sweep structural high.
                if float(current["high"]) > state["structural_extreme"]:
                    state["structural_extreme"] = float(current["high"])
                    state["structural_time"] = current_time

                break_level = state.get("break_level")

                if (
                    break_level is not None
                    and float(current["close"]) < float(break_level)
                ):
                    return self._confirm(
                        state,
                        current,
                        current_time,
                    )

            return None

        # ------------------------------------------------------------
        # New liquidity sweep.
        # ------------------------------------------------------------
        low_level = _latest_confirmed_pivot(
            hourly,
            "low",
            int(self.params["liquidity_pivot_left"]),
            int(self.params["liquidity_pivot_right"]),
        )

        high_level = _latest_confirmed_pivot(
            hourly,
            "high",
            int(self.params["liquidity_pivot_left"]),
            int(self.params["liquidity_pivot_right"]),
        )

        swept_low = (
            low_level is not None
            and float(current["low"]) < float(low_level["price"])
        )

        swept_high = (
            high_level is not None
            and float(current["high"]) > float(high_level["price"])
        )

        # Ambiguous giant candle sweeping both sides.
        if swept_low and swept_high:
            return None

        if swept_low and direction in {"both", "long"}:
            swing = _meaningful_pre_sweep_swing(
                one,
                kind="high",
                sweep_time=current_time,
                left=int(self.params["execution_pivot_left"]),
                right=int(self.params["execution_pivot_right"]),
                lookback_bars=int(self.params["structure_lookback_bars"]),
                minimum_structure_bars=int(
                    self.params["minimum_structure_bars"]
                ),
            )

            if swing is None:
                return None

            self._state = {
                "direction": "long",
                "liquidity_price": float(low_level["price"]),
                "liquidity_time": low_level["time"],
                "sweep_time": current_time,
                "sweep_price": float(current["low"]),
                "structural_extreme": float(current["low"]),
                "structural_time": current_time,
                "break_level": float(swing["price"]),
                "break_level_time": swing["time"],
                "bars_waited": 0,
            }

        elif swept_high and direction in {"both", "short"}:
            swing = _meaningful_pre_sweep_swing(
                one,
                kind="low",
                sweep_time=current_time,
                left=int(self.params["execution_pivot_left"]),
                right=int(self.params["execution_pivot_right"]),
                lookback_bars=int(self.params["structure_lookback_bars"]),
                minimum_structure_bars=int(
                    self.params["minimum_structure_bars"]
                ),
            )

            if swing is None:
                return None

            self._state = {
                "direction": "short",
                "liquidity_price": float(high_level["price"]),
                "liquidity_time": high_level["time"],
                "sweep_time": current_time,
                "sweep_price": float(current["high"]),
                "structural_extreme": float(current["high"]),
                "structural_time": current_time,
                "break_level": float(swing["price"]),
                "break_level_time": swing["time"],
                "bars_waited": 0,
            }

        return None

    def _confirm(
        self,
        state: dict,
        current: pd.Series,
        confirmation_time: datetime,
    ) -> EntrySignal | None:
        retrace = float(self.params.get("entry_retrace", 0.5))
        target_r = float(self.params.get("target_r", 1.5))

        if state["direction"] == "long":
            impulse_low = float(state["structural_extreme"])
            impulse_high = float(current["high"])

            entry = impulse_low + (
                impulse_high - impulse_low
            ) * retrace

            stop = impulse_low
            risk = entry - stop
            target = entry + risk * target_r

        else:
            impulse_high = float(state["structural_extreme"])
            impulse_low = float(current["low"])

            entry = impulse_high - (
                impulse_high - impulse_low
            ) * retrace

            stop = impulse_high
            risk = stop - entry
            target = entry - risk * target_r

        self._state = None

        if risk <= 0:
            return None

        metadata = {
            "strategy_version": "xau_liquidity_type3_baseline_v1_1",
            "session": _session_label(confirmation_time),

            "liquidity_level": state["liquidity_price"],
            "liquidity_level_time": state["liquidity_time"].isoformat(),

            "sweep_time": state["sweep_time"].isoformat(),
            "sweep_price": state["sweep_price"],
            "sweep_size": abs(
                float(state["sweep_price"])
                - float(state["liquidity_price"])
            ),

            "type3_confirmation_time": confirmation_time.isoformat(),

            "swing_level_broken": float(state["break_level"]),
            "swing_level_time": (
                state["break_level_time"].isoformat()
                if state.get("break_level_time")
                else None
            ),

            "impulse_high": impulse_high,
            "impulse_low": impulse_low,

            "entry_retrace": retrace,
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "target_r": target_r,
        }

        return EntrySignal(
            state["direction"],
            stop_loss=stop,
            take_profit=target,
            reason="liquidity_sweep_type3_50pct",
            metadata=metadata,
            order_type="limit",
            entry_price=entry,
            max_wait_bars=int(self.params["limit_wait_bars"]),
        )


def _meaningful_pre_sweep_swing(
    frame: pd.DataFrame,
    kind: str,
    sweep_time: datetime,
    left: int,
    right: int,
    lookback_bars: int,
    minimum_structure_bars: int,
):
    """
    Select a meaningful opposing swing before the sweep.

    Difference from baseline v1:
    - do not simply take the latest tiny pivot;
    - search a bounded pre-sweep region;
    - reject pivots immediately beside the sweep;
    - prefer the strongest structural pivot in that region.

    For a long:
        choose the highest confirmed pivot-high in the pre-sweep leg.

    For a short:
        choose the lowest confirmed pivot-low in the pre-sweep leg.
    """

    if frame is None or len(frame) < left + right + 1:
        return None

    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    sweep_ts = pd.Timestamp(sweep_time)

    eligible_indexes = [
        i
        for i in range(len(frame))
        if timestamps.iloc[i] < sweep_ts
    ]

    if not eligible_indexes:
        return None

    sweep_index = eligible_indexes[-1] + 1

    start_index = max(
        left,
        sweep_index - lookback_bars,
    )

    end_index = min(
        sweep_index - minimum_structure_bars,
        len(frame) - right,
    )

    if end_index <= start_index:
        return None

    pivots = []

    values = pd.to_numeric(
        frame[kind],
        errors="coerce",
    ).tolist()

    for i in range(start_index, end_index):
        value = float(values[i])

        left_values = [
            float(x)
            for x in values[i - left : i]
        ]

        right_values = [
            float(x)
            for x in values[i + 1 : i + 1 + right]
        ]

        if kind == "high":
            valid = (
                value > max(left_values)
                and value >= max(right_values)
            )
        else:
            valid = (
                value < min(left_values)
                and value <= min(right_values)
            )

        if not valid:
            continue

        pivots.append(
            {
                "time": _ts(timestamps.iloc[i]),
                "price": value,
                "index": i,
            }
        )

    if not pivots:
        return None

    if kind == "high":
        # For long Type 3, choose the strongest pre-sweep high.
        return max(
            pivots,
            key=lambda item: (
                item["price"],
                item["index"],
            ),
        )

    # For short Type 3, choose the strongest pre-sweep low.
    return min(
        pivots,
        key=lambda item: (
            item["price"],
            -item["index"],
        ),
    )


def _latest_confirmed_pivot(
    frame: pd.DataFrame,
    kind: str,
    left: int,
    right: int,
    before: datetime | None = None,
):
    if frame is None or len(frame) < left + right + 1:
        return None

    values = pd.to_numeric(
        frame[kind],
        errors="coerce",
    ).tolist()

    timestamps = pd.to_datetime(
        frame["timestamp"],
        utc=True,
    )

    last = None

    for i in range(
        left,
        len(frame) - right,
    ):
        stamp = _ts(timestamps.iloc[i])

        if before is not None and stamp >= before:
            continue

        value = float(values[i])

        left_values = [
            float(x)
            for x in values[i - left : i]
        ]

        right_values = [
            float(x)
            for x in values[i + 1 : i + 1 + right]
        ]

        if (
            kind == "low"
            and value < min(left_values)
            and value <= min(right_values)
        ):
            last = {
                "time": stamp,
                "price": value,
            }

        elif (
            kind == "high"
            and value > max(left_values)
            and value >= max(right_values)
        ):
            last = {
                "time": stamp,
                "price": value,
            }

    return last


def _session_label(
    when: datetime,
) -> str:
    active: list[str] = []

    tokyo = when.astimezone(TOKYO).time()
    london = when.astimezone(LONDON).time()
    new_york = when.astimezone(NEW_YORK).time()

    if 9 <= tokyo.hour < 18:
        active.append("Asia")

    if 8 <= london.hour < 17:
        active.append("London")

    if 8 <= new_york.hour < 17:
        active.append("New York")

    if not active:
        return "Outside named sessions"

    label = " / ".join(active)

    if len(active) > 1:
        label += " overlap"

    return label


def _ts(value) -> datetime:
    stamp = pd.Timestamp(value)

    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")

    return stamp.to_pydatetime()