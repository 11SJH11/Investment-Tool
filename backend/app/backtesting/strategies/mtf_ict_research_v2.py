"""Research-only MTF ablations and ICT confluence hypotheses, October 2026.

Requires the separately installed, FROZEN experimental_strategy_batch_2026_v1.py.
All operations use StrategyContext.completed bars and return Ledger EntrySignals;
no broker IO, order submission, network calls, or model access occurs here.

Research hypotheses, not validated predictive relationships. 2025 Jan-Sep
has already been inspected. Keep later validation data out of development.
"""
from __future__ import annotations

from dataclasses import replace
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from app.backtesting.models import EntrySignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry
from app.backtesting.strategies.experimental_strategy_batch_2026_v1 import (
    DailyHourlyFiveMinNoBias,
)

SOURCE = "backend/app/backtesting/strategies/mtf_ict_research_v2.py"


@strategy_registry.register
class MTFV2ALongOnly(DailyHourlyFiveMinNoBias):
    """Ablation of shorts, otherwise the same setup and engine-owned exits."""

    spec = replace(
        DailyHourlyFiveMinNoBias.spec,
        key="mtf_v2a_h1_m5_long_only",
        name="MTF V2A · 1H/5m long-only",
        description=(
            "Frozen no-daily-bias 1H/5m rules, but ignore short breakouts. "
            "The parent strategy and its previous runs remain unchanged."
        ),
        source_file=SOURCE,
    )

    def on_bar(self, ctx):
        # Discard bearish *pending* breakouts, not just the eventual short trade.
        # A skipped setup does not consume the calendar day.
        if self.state is not None and self.state.get("direction") == "short":
            self.state = None
        out = super().on_bar(ctx)
        if self.state is not None and self.state.get("direction") == "short":
            self.state = None
        if isinstance(out, EntrySignal):
            if out.direction != "long":
                return None
            return replace(
                out,
                metadata={**out.metadata, "research_variant": "MTF_V2A_long_only"},
            )
        return out


@strategy_registry.register
class MTFV2CLevelProximity(DailyHourlyFiveMinNoBias):
    """Filter confirmation candles that have chased too far from frozen 1H level.

    Measure distance at signal time, divided by signal-close to *planned* stop.
    This is NOT measured using next open, which would introduce future data.
    Rejected parent signals still consume that day's parent opportunity.
    """

    spec = replace(
        DailyHourlyFiveMinNoBias.spec,
        key="mtf_v2c_h1_m5_max_level_distance_050r",
        name="MTF V2C · 1H/5m ≤0.5R from level",
        description=(
            "No-daily-bias 1H/5m setup; filter signals whose confirmation close "
            "is farther than 0.5 planned-risk units from the frozen 1H level."
        ),
        defaults={**DailyHourlyFiveMinNoBias.spec.defaults, "max_level_distance_r": 0.5},
        research_parameters=(*DailyHourlyFiveMinNoBias.spec.research_parameters,
                             ParameterSpec("max_level_distance_r", "Max confirmation/level distance R",
                                           "float", 0.5, 0.1, 2.0, 0.1)),
        source_file=SOURCE,
    )

    def on_bar(self, ctx):
        out = super().on_bar(ctx)
        if not isinstance(out, EntrySignal):
            return out
        if out.stop_loss is None:
            return None
        level = out.metadata.get("hourly_breakout_level")
        if level is None:
            return None
        # A completed 5m close exists when the parent's entry signal was created.
        close = float(ctx.current_bar["close"])
        stop = float(out.stop_loss)
        risk = abs(close - stop)
        if not all(isfinite(v) for v in (close, stop, float(level))) or risk <= 0:
            return None
        distance_r = abs(close - float(level)) / risk
        if distance_r > float(self.params["max_level_distance_r"]):
            return None
        return replace(
            out,
            metadata={**out.metadata,
                      "research_variant": "MTF_V2C_level_proximity",
                      "confirmed_close": close,
                      "level_distance_r_at_signal": distance_r,
                      "max_level_distance_r": float(self.params["max_level_distance_r"])},
        )


# ---- Standalone ICT confluence screening: explicitly simplified definitions. ----
# Five categories: liquidity sweep, 5m BOS, 5m FVG/IFVG, 50%-78.6% fib
# retracement, and last-opposing-candle (order-block proxy) retest.
# Liquidity sweep + BOS + fib are mandatory for all three score variants.
# ICT concepts are subjective; these fixed rules do NOT replicate a named model.


def _v(row, field: str) -> float:
    return float(row[field])


def _stamp(row) -> pd.Timestamp:
    t = pd.Timestamp(row["timestamp"])
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _ohlc_ok(frame: pd.DataFrame, minimum: int = 1) -> bool:
    if frame is None or len(frame) < minimum or not {"timestamp", "open", "high", "low", "close"}.issubset(frame):
        return False
    try:
        f = frame.tail(minimum)[["open", "high", "low", "close"]].astype(float)
        return bool(f.map(isfinite).all().all() and
                    (f["high"] >= f[["open", "low", "close"]].max(axis=1)).all() and
                    (f["low"] <= f[["open", "high", "close"]].min(axis=1)).all())
    except (ValueError, TypeError):
        return False


def _atr5(bars: pd.DataFrame, n: int = 14) -> float | None:
    if not _ohlc_ok(bars, n + 1):
        return None
    sample = bars.tail(n + 1)
    prev = sample.close.astype(float).shift(1)
    true_range = pd.concat([
        sample.high.astype(float) - sample.low.astype(float),
        (sample.high.astype(float) - prev).abs(),
        (sample.low.astype(float) - prev).abs(),
    ], axis=1).max(axis=1)
    result = float(true_range.iloc[1:].mean())
    return result if isfinite(result) and result > 0 else None


def _recent_pivot(bars: pd.DataFrame, kind: str, left: int = 2, right: int = 2):
    """Latest swing confirmed by `right` ALREADY COMPLETED subsequent bars."""
    if kind not in ("high", "low") or not _ohlc_ok(bars, left + right + 1):
        return None
    values = bars[kind].astype(float).tolist()
    for i in range(len(values) - right - 1, left - 1, -1):
        val = values[i]
        before = values[i-left:i]
        after = values[i+1:i+1+right]
        if kind == "high" and val > max(before) and val >= max(after):
            return {"price": val, "time": _stamp(bars.iloc[i])}
        if kind == "low" and val < min(before) and val <= min(after):
            return {"price": val, "time": _stamp(bars.iloc[i])}
    return None


def _three_candle_fvg(bars: pd.DataFrame):
    """At close of bar C: bullish if C.low > A.high; bearish if C.high < A.low.

    Do not bridge missing 5m bars because price discontinuities are not an FVG.
    """
    if not _ohlc_ok(bars, 3):
        return None
    a, mid, c = (bars.iloc[-3], bars.iloc[-2], bars.iloc[-1])
    if (_stamp(mid) - _stamp(a) != pd.Timedelta(minutes=5) or
        _stamp(c) - _stamp(mid) != pd.Timedelta(minutes=5)):
        return None
    if _v(c, "low") > _v(a, "high"):
        return {"direction": "long", "lower": _v(a, "high"), "upper": _v(c, "low"),
                "time": _stamp(c), "kind": "FVG"}
    if _v(c, "high") < _v(a, "low"):
        return {"direction": "short", "lower": _v(c, "high"), "upper": _v(a, "low"),
                "time": _stamp(c), "kind": "FVG"}
    return None


def _zone_intersects(a: tuple[float, float], b: tuple[float, float], *, tolerance: float = 0.0) -> bool:
    return a[0] <= b[1] + tolerance and b[0] <= a[1] + tolerance


def _fib_retracement_zone(direction: str, low: float, high: float) -> tuple[float, float]:
    if high <= low or not all(isfinite(x) for x in (high, low)):
        raise ValueError("Invalid impulse extremes")
    width = high - low
    if direction == "long":
        return high - 0.786 * width, high - 0.5 * width
    if direction == "short":
        return low + 0.5 * width, low + 0.786 * width
    raise ValueError("Invalid direction")


def _opposing_candle_zone(bars: pd.DataFrame, direction: str):
    """Order-block *proxy*: last opposite-colour completed 5m candle before BOS."""
    # Caller gives pre-BOS candles; this never uses a future candle as a zone.
    if not _ohlc_ok(bars, 1):
        return None
    for _, row in bars.tail(10).iloc[::-1].iterrows():
        up = _v(row, "close") > _v(row, "open")
        down = _v(row, "close") < _v(row, "open")
        if (direction == "long" and down) or (direction == "short" and up):
            return {"low": _v(row, "low"), "high": _v(row, "high"), "time": _stamp(row)}
    return None


_ICT_DEFAULTS = {
    "direction": "both", "hourly_pivot_left": 2, "hourly_pivot_right": 2,
    "structure_pivot_left": 2, "structure_pivot_right": 2,
    "max_sweep_to_bos_bars": 18, "max_bos_to_retest_bars": 24,
    "sweep_buffer_atr5": 0.05, "stop_buffer_atr5": 0.05,
    "max_pivot_age_hours": 72, "target_r": 2.0,
    "fvg_overlap_tolerance_atr5": 0.15,
}


class _ICTCombinedConfluences(Strategy):
    MIN_CONFLUENCES = 3
    spec = StrategySpec(
        key="_ict_confluence_base", name="Base (not registered)", category="Experimental ICT",
        description="Liquidity sweep -> 5m BOS -> 50%-78.6% fib retest; optional gap + OB confluence.",
        timeframes=("5m", "1h"), defaults=_ICT_DEFAULTS,
        parameters=(ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),),
        research_parameters=(ParameterSpec("target_r", "Fixed target R", "float", 2.0, 0.5, 5.0, 0.25),),
        risk_management={
            "Entry": "Next 5m bar open after completed fib-zone reversal signal",
            "Liquidity": "Sweep/reclaim of last 2L/2R-confirmed 1h pivot; at most 72h old",
            "BOS": "Completed 5m close through opposite confirmed 2L/2R pivot frozen at sweep",
            "FVG/IFVG": "5m three-candle directional gap or inversion of opposite gap; overlaps fib zone",
            "Fib": "50% to 78.6% retracement of sweep-extreme → BOS impulse",
            "Order block": "Last opposing 5m candle before BOS; retest overlaps fib bar",
            "Stop": "Beyond liquidity-sweep extreme + 0.05 × 5m ATR buffer",
            "Target": "Fixed 2R from actual next-open fill",
            "Frequency": "First completed qualifying setup per NY date; no same-bar BOS and fib retest",
        },
        source_file=SOURCE,
    )

    def __init__(self, **params):
        super().__init__(**params)
        self.reset()

    def reset(self):
        self.state: dict | None = None
        self.last5: pd.Timestamp | None = None
        self.used_days: set = set()

    def _new_sweep(self, bars, hourly, v_atr, current, previous, now):
        # Look at LAST 1h pivots that were fully confirmed at sweep time.
        candidates = []
        for direction, kind in (("long", "low"), ("short", "high")):
            if self.params["direction"] not in ("both", direction):
                continue
            h = _recent_pivot(hourly, kind, int(self.params["hourly_pivot_left"]),
                              int(self.params["hourly_pivot_right"]))
            if h is None or now - h["time"] > pd.Timedelta(hours=float(self.params["max_pivot_age_hours"])):
                continue
            buffer = float(self.params["sweep_buffer_atr5"]) * v_atr
            if direction == "long":
                qualifies = (_v(current, "low") < h["price"] - buffer and
                             _v(current, "close") > h["price"] and
                             _v(previous, "close") >= h["price"] - buffer)
                extreme = _v(current, "low")
                bos = _recent_pivot(bars.iloc[:-1], "high", int(self.params["structure_pivot_left"]),
                                    int(self.params["structure_pivot_right"]))
            else:
                qualifies = (_v(current, "high") > h["price"] + buffer and
                             _v(current, "close") < h["price"] and
                             _v(previous, "close") <= h["price"] + buffer)
                extreme = _v(current, "high")
                bos = _recent_pivot(bars.iloc[:-1], "low", int(self.params["structure_pivot_left"]),
                                    int(self.params["structure_pivot_right"]))
            if qualifies and bos is not None:
                candidates.append((direction, h, bos, extreme))
        # Both-side sweep on one OHLC bar has unknowable intrabar order; reject.
        if len(candidates) != 1:
            return None
        direction, liquidity, bos, extreme = candidates[0]
        return {
            "stage": "SWEEP", "direction": direction, "sweep_at": now,
            "last_at": now, "stage_bars": 0,
            "liquidity": liquidity, "bos": bos, "sweep_extreme": extreme,
            "gap_events": [], "atr_at_sweep": v_atr,
        }

    def _update_gap_events(self, state, bars, now):
        gap = _three_candle_fvg(bars)
        if gap is not None and gap["time"] > state["sweep_at"]:
            state["gap_events"].append(gap)
        # A bearish gap inverted to bullish is a bullish IFVG, and vice versa.
        current, prev = bars.iloc[-1], bars.iloc[-2]
        new_inversions = []
        for saved in state["gap_events"]:
            if saved["time"] >= now or saved["kind"] != "FVG":
                continue
            if (saved["direction"] == "short" and
                _v(prev, "close") <= saved["upper"] < _v(current, "close")):
                new_inversions.append({**saved, "direction": "long", "time": now, "kind": "IFVG"})
            elif (saved["direction"] == "long" and
                  _v(prev, "close") >= saved["lower"] > _v(current, "close")):
                new_inversions.append({**saved, "direction": "short", "time": now, "kind": "IFVG"})
        state["gap_events"].extend(new_inversions)
        # Keep a bounded event trail for reproducibility and performance.
        state["gap_events"] = state["gap_events"][-40:]

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "5m" or ctx.position is not None:
            return None
        bars = ctx.bars("5m", count=130)
        if not _ohlc_ok(bars, 35):
            return None
        now = _stamp(bars.iloc[-1])
        if self.last5 == now:
            return None
        self.last5 = now
        today = ctx.decision_time.astimezone(ZoneInfo("America/New_York")).date()
        if today in self.used_days:
            return None
        atr = _atr5(bars)
        if atr is None:
            return None
        current, previous = bars.iloc[-1], bars.iloc[-2]
        if self.state is None:
            hourly = ctx.bars("1h", count=100)
            if not _ohlc_ok(hourly, 12):
                return None
            self.state = self._new_sweep(bars, hourly, atr, current, previous, now)
            return None

        s = self.state
        s["stage_bars"] += 1
        s["last_at"] = now
        self._update_gap_events(s, bars, now)
        direction = s["direction"]
        if s["stage"] == "SWEEP":
            if s["stage_bars"] > int(self.params["max_sweep_to_bos_bars"]):
                self.state = None
                return None
            if direction == "long":
                s["sweep_extreme"] = min(s["sweep_extreme"], _v(current, "low"))
                if _v(current, "close") <= s["sweep_extreme"]:
                    self.state = None
                    return None
                crossed = _v(previous, "close") <= s["bos"]["price"] < _v(current, "close")
            else:
                s["sweep_extreme"] = max(s["sweep_extreme"], _v(current, "high"))
                if _v(current, "close") >= s["sweep_extreme"]:
                    self.state = None
                    return None
                crossed = _v(previous, "close") >= s["bos"]["price"] > _v(current, "close")
            if not crossed:
                return None
            # The impulse includes all COMPLETED 5m bars since the sweep.
            # 130-bar context is longer than the permitted setup age.
            recent = bars.loc[pd.to_datetime(bars.timestamp, utc=True) >= s["sweep_at"]]
            if recent.empty:
                return None
            s["impulse_low"] = float(recent.low.min())
            s["impulse_high"] = float(recent.high.max())
            if s["impulse_high"] <= s["impulse_low"]:
                self.state = None
                return None
            s["fib"] = _fib_retracement_zone(direction, s["impulse_low"], s["impulse_high"])
            s["ob"] = _opposing_candle_zone(bars.iloc[:-1], direction)
            s["stage"] = "BOS"
            s["stage_bars"] = 0
            s["bos_at"] = now
            return None

        if s["stage_bars"] > int(self.params["max_bos_to_retest_bars"]):
            self.state = None
            return None
        stop = (s["sweep_extreme"] - float(self.params["stop_buffer_atr5"]) * atr
                if direction == "long" else
                s["sweep_extreme"] + float(self.params["stop_buffer_atr5"]) * atr)
        close = _v(current, "close")
        if (direction == "long" and close <= stop) or (direction == "short" and close >= stop):
            self.state = None
            return None
        fib = s["fib"]
        touched_fib = _zone_intersects((_v(current, "low"), _v(current, "high")), fib)
        reversal = (_v(current, "close") > _v(current, "open") and close > fib[0]
                    if direction == "long" else
                    _v(current, "close") < _v(current, "open") and close < fib[1])
        if not (touched_fib and reversal):
            return None
        # Entry's structure requires sweep + BOS + fib. Gap and OB are optional
        # confirmations for the less restrictive threshold; all are evidenced.
        relevant_gap = next((g for g in reversed(s["gap_events"])
                             if g["direction"] == direction and
                             _zone_intersects((g["lower"], g["upper"]), fib,
                                              tolerance=float(self.params["fvg_overlap_tolerance_atr5"]) * atr)), None)
        ob = s.get("ob")
        ob_held = bool(ob and
                       _zone_intersects((ob["low"], ob["high"]),
                                        (_v(current, "low"), _v(current, "high"))) and
                       (close >= ob["low"] if direction == "long" else close <= ob["high"]))
        flags = {"liquidity_sweep": True, "confirmed_5m_bos": True,
                 "fvg_or_ifvg": relevant_gap is not None,
                 "fib_50_786_retest": True,
                 "opposing_candle_ob_proxy": ob_held}
        score = sum(flags.values())
        # Consume the candidate even if it fails the chosen score threshold;
        # don't cherry-pick a later entry on the same impulse.
        self.state = None
        self.used_days.add(today)
        if score < self.MIN_CONFLUENCES:
            return None
        out = EntrySignal(
            direction=direction, stop_loss=stop,
            target_r=float(self.params["target_r"]),
            reason=f"ict_{self.MIN_CONFLUENCES}of5_sweep_bos_fib",
            metadata={
                "family": "ICT_confluence_screening", "variant_score_threshold": self.MIN_CONFLUENCES,
                "score": score, "flags": flags,
                "liquidity_level": s["liquidity"]["price"],
                "liquidity_pivot_time": s["liquidity"]["time"].isoformat(),
                "sweep_at": s["sweep_at"].isoformat(),
                "sweep_extreme": s["sweep_extreme"],
                "bos_level": s["bos"]["price"],
                "bos_at": s["bos_at"].isoformat(),
                "impulse_low": s["impulse_low"], "impulse_high": s["impulse_high"],
                "fib_zone": list(fib),
                "order_block_proxy": ({"low": ob["low"], "high": ob["high"],
                                       "time": ob["time"].isoformat()} if ob else None),
                "fvg_or_ifvg": ({"kind": relevant_gap["kind"], "direction": relevant_gap["direction"],
                                 "lower": relevant_gap["lower"], "upper": relevant_gap["upper"],
                                 "time": relevant_gap["time"].isoformat()} if relevant_gap else None),
                "signal_close": close, "initial_stop": stop,
                "model_scope": "mechanical_ict_proxies_not_verified_ict_rules",
            },
        )
        return out


@strategy_registry.register
class ICTC03ThreeOfFive(_ICTCombinedConfluences):
    MIN_CONFLUENCES = 3
    spec = replace(_ICTCombinedConfluences.spec,
                   key="ict_confluence_c03_three_of_five_v1",
                   name="ICT C03 · sweep/BOS/fib (3 of 5)",
                   description="Standalone ICT-inspired: required 1h sweep, 5m BOS and 50–78.6 fib retest; record optional FVG/IFVG and OB proxy.")


@strategy_registry.register
class ICTC04FourOfFive(_ICTCombinedConfluences):
    MIN_CONFLUENCES = 4
    spec = replace(_ICTCombinedConfluences.spec,
                   key="ict_confluence_c04_four_of_five_v1",
                   name="ICT C04 · 4/5 confluence score",
                   description="C03 plus at least one: fib-zone overlapping 5m FVG/IFVG or last-opposing-candle order-block proxy retest.")


@strategy_registry.register
class ICTC05AllFive(_ICTCombinedConfluences):
    MIN_CONFLUENCES = 5
    spec = replace(_ICTCombinedConfluences.spec,
                   key="ict_confluence_c05_all_five_v1",
                   name="ICT C05 · all 5 confluences",
                   description="C03 plus BOTH fib-zone overlapping directional FVG/IFVG and OB proxy retest. Very selective; may trade rarely.")
