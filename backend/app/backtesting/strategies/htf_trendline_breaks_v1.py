"""Ledger HTF trendline research suite, v1 (research/backtest ONLY).

Eight registered strategies (15m/30m/1h/4h, 15m+1h, 15m+4h, 1h+4h,
15m+1h+4h). 1m is the execution/optional retest cadence ONLY.

All HTF bars come from StrategyContext.bars: completed bars only. Pivot
confirmation requires two COMPLETE right-hand bars. To detect a break, a
trendline must have existed before the breakout candle and a THIRD independent,
confirmed pivot touch. No future bars, no trade outcome selection.

Conventions: OHLC timestamps are UTC bar OPEN, as in Ledger Strategy Lab.
UI drawings are stored in EntrySignal.metadata['chart_drawings']; see the
separate chart adapter in this distribution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Any
import math

import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry

TF_MINUTES = {"1m": 1, "15m": 15, "30m": 30, "1h": 60, "4h": 240}
PIVOT_W = 2
LOOKBACK = 180
MIN_PIVOT_GAP = 4
MAX_PIVOTS_PER_SIDE = 24
MAX_LINE_AGE_BARS = 48
MAX_SLOPE_ATR_PER_BAR = 0.85
MIN_SLOPE_ATR_PER_BAR = 0.015


def _stamp(obj: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(obj)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _iso(t: Any) -> str:
    return _stamp(t).isoformat().replace("+00:00", "Z")


def _at(t: pd.Timestamp) -> float:
    return _stamp(t).timestamp()


def _project(t1: Any, p1: float, t2: Any, p2: float, at: Any) -> float:
    x1, x2, x = _at(t1), _at(t2), _at(at)
    if x2 <= x1:
        raise ValueError("non-increasing trendline anchors")
    return p1 + (p2 - p1) * ((x - x1) / (x2 - x1))


def _atr_value(df: pd.DataFrame, period: int = 14) -> float:
    # Use only data available at time of evaluation.
    previous_close = df["close"].shift(1)
    tr = pd.concat([(df["high"]-df["low"]).abs(),
                    (df["high"]-previous_close).abs(),
                    (df["low"]-previous_close).abs()], axis=1).max(axis=1)
    val = float(tr.tail(period).mean())
    return val if math.isfinite(val) and val > 0 else 0.0


def _pivots(frame: pd.DataFrame, side: str, atr: float,
            prominence_atr: float) -> list[int]:
    # i is eligible only after PIVOT_W later bars have completed.
    arr = frame["low" if side == "support" else "high"].to_numpy(dtype=float)
    out: list[int] = []
    for i in range(PIVOT_W, len(arr) - PIVOT_W):
        segment = arr[i-PIVOT_W:i+PIVOT_W+1]
        before = arr[i-PIVOT_W:i]
        after = arr[i+1:i+PIVOT_W+1]
        if side == "support":
            if (arr[i] == min(segment) and sum(v == arr[i] for v in segment) == 1
                    and min(float(before.min()), float(after.min())) - arr[i] >= prominence_atr*atr):
                out.append(i)
        else:
            if (arr[i] == max(segment) and sum(v == arr[i] for v in segment) == 1
                    and arr[i] - max(float(before.max()), float(after.max())) >= prominence_atr*atr):
                out.append(i)
    return out[-MAX_PIVOTS_PER_SIDE:]


@dataclass(frozen=True)
class _Line:
    side: str
    timeframe: str
    t1: str
    p1: float
    t2: str
    p2: float
    confirmed_at: str
    last_touch_at: str
    touches: tuple[tuple[str, float], ...]
    atr: float

    def value(self, when: Any) -> float:
        return _project(self.t1, self.p1, self.t2, self.p2, when)

    def drawing(self, breakout_at: Any, *, role: str = "trigger") -> dict[str, Any]:
        return {
            "type": "trend_line", "role": role, "timeframe": self.timeframe,
            "side": self.side, "t1": self.t1, "p1": self.p1,
            "t2": self.t2, "p2": self.p2,
            "confirmed_at": self.confirmed_at,
            "breakout_at": _iso(breakout_at),
            "breakout_price_on_line": round(self.value(breakout_at), 8),
            "touches": [{"time": t, "price": p} for t, p in self.touches],
            "style": {"color": "#e35e5e" if self.side == "support" else "#39b89f", "width": 2},
            "provenance": "recorded_at_signal", "schema_version": 1,
        }


def _candidates(previous: pd.DataFrame, side: str, tf: str,
                min_touches: int, touch_atr: float, prominence_atr: float = 0.20) -> list[_Line]:
    """Fit against pre-break CLOSED bars. Never select from future/current break bar."""
    if len(previous) < 28:
        return []
    previous = previous.tail(LOOKBACK).reset_index(drop=True)
    atr = _atr_value(previous)
    if atr <= 0:
        return []
    pivots = _pivots(previous, side, atr, prominence_atr)
    if len(pivots) < min_touches:
        return []
    key = "low" if side == "support" else "high"
    # Vectorize price/time projection: called once per completed HTF bar for
    # potentially years of 1m-led runs. Do not parse a Timestamp per comparison.
    t = pd.to_datetime(previous["timestamp"], utc=True)
    secs = (t.astype("int64") // 10**9).to_numpy(dtype=float)
    prices = previous[key].to_numpy(dtype=float)
    closes = previous["close"].to_numpy(dtype=float)
    results: list[_Line] = []

    # Enumerate anchor pairs. Third+ touches must be LATER distinct pivots.
    for a, b in combinations(pivots, 2):
        if b-a < MIN_PIVOT_GAP or secs[b] <= secs[a]:
            continue
        p1, p2 = float(prices[a]), float(prices[b])
        if side == "support" and p2 <= p1:
            continue
        if side == "resistance" and p2 >= p1:
            continue
        slope_atr = abs((p2-p1)/(b-a))/atr
        if not MIN_SLOPE_ATR_PER_BAR <= slope_atr <= MAX_SLOPE_ATR_PER_BAR:
            continue
        slope_per_second = (p2-p1) / (secs[b]-secs[a])
        indices = pd.Index(range(b+1, len(previous))).to_numpy(dtype=int)
        boundary = p1 + slope_per_second*(secs[indices]-secs[a])
        breached = (closes[indices] < boundary - 0.18*atr) if side == "support" else (
            closes[indices] > boundary + 0.18*atr)
        if bool(breached.any()):
            continue
        valid_touches = [(a, p1), (b, p2)]
        for c in pivots:
            if c <= b or c-valid_touches[-1][0] < MIN_PIVOT_GAP:
                continue
            predicted = p1 + slope_per_second*(secs[c]-secs[a])
            if abs(float(prices[c])-predicted) <= touch_atr*atr:
                valid_touches.append((c, float(prices[c])))
        if len(valid_touches) < min_touches:
            continue
        third_at = valid_touches[min_touches-1][0]
        if third_at + PIVOT_W >= len(previous):
            # A pivot is not known at its apex; right-hand bars must have closed.
            continue
        if (len(previous)-1)-valid_touches[-1][0] > MAX_LINE_AGE_BARS:
            continue
        # Pivot time is candle OPEN; confirmation is CLOSE of right-hand bar.
        confirmed_open = t.iloc[third_at+PIVOT_W]
        available = confirmed_open+pd.Timedelta(minutes=TF_MINUTES[tf])
        results.append(_Line(
            side=side, timeframe=tf, t1=_iso(t.iloc[a]), p1=p1,
            t2=_iso(t.iloc[b]), p2=p2, confirmed_at=_iso(available),
            last_touch_at=_iso(t.iloc[valid_touches[-1][0]]),
            touches=tuple((_iso(t.iloc[i]), p) for i, p in valid_touches),
            atr=atr,
        ))
    # Deterministic, outcome-INDEPENDENT ranking.
    results.sort(key=lambda line: (len(line.touches), line.last_touch_at,
                                   line.t1, line.t2), reverse=True)
    return results[:6]


def _breakout(frame: pd.DataFrame, tf: str, min_touches: int,
              touch_atr: float, break_atr: float, prominence_atr: float = 0.20) -> dict[str, Any] | None:
    if len(frame) < 30:
        return None
    frame = frame.tail(LOOKBACK+1).reset_index(drop=True)
    previous = frame.iloc[:-1]
    current = frame.iloc[-1]
    prev = frame.iloc[-2]
    now_at = _stamp(current["timestamp"])
    prev_at = _stamp(prev["timestamp"])
    # Current ATR exists at the close of the breakout candle (causal).
    current_atr = _atr_value(frame)
    if current_atr <= 0:
        return None
    hits: list[tuple[float, _Line, str, float]] = []
    for side, direction in (("support", "short"), ("resistance", "long")):
        for line in _candidates(previous, side, tf, min_touches, touch_atr, prominence_atr):
            if _stamp(line.confirmed_at) > now_at:
                continue  # was not known before current candle opened
            curr_line = line.value(now_at)
            prev_line = line.value(prev_at)
            if direction == "short":
                crossed = (float(prev["close"]) >= prev_line - 0.18*line.atr and
                           float(current["close"]) < curr_line - break_atr*current_atr)
                distance = curr_line - float(current["close"])
            else:
                crossed = (float(prev["close"]) <= prev_line + 0.18*line.atr and
                           float(current["close"]) > curr_line + break_atr*current_atr)
                distance = float(current["close"]) - curr_line
            if crossed:
                # Prefer objectively longer-standing/more-touched structure.
                strength = 10*len(line.touches) + min(10, abs(distance)/current_atr)
                hits.append((strength, line, direction, curr_line))
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0], h[1].last_touch_at, h[1].t1), reverse=True)
    _, line, direction, boundary = hits[0]
    return {
        "tf": tf, "direction": direction,
        "broken_bar_start": _iso(now_at),
        "confirmed_at": _iso(now_at + pd.Timedelta(minutes=TF_MINUTES[tf])),
        "bar_high": float(current["high"]),
        "bar_low": float(current["low"]),
        "line_at_break": boundary,
        "atr": current_atr, "line": line,
    }


class _TrendlineBase(Strategy):
    FRAME_SET: tuple[str, ...] = ()

    def __init__(self, **params):
        super().__init__(**params)
        self.reset()

    def reset(self) -> None:
        self._processed: dict[str, str] = {}
        self._events: dict[str, dict[str, Any]] = {}
        self._last_signature: tuple[Any, ...] | None = None
        self._last_signal_time: pd.Timestamp | None = None
        self._pending: dict[str, Any] | None = None

    def _scan(self, ctx) -> None:
        for tf in self.FRAME_SET:
            df = ctx.bars(tf, count=LOOKBACK+1)
            if len(df) < 30:
                continue
            newest = _iso(df.iloc[-1]["timestamp"])
            # Defensive guard if a provider leaks the still-open HTF candle.
            if _stamp(newest) + pd.Timedelta(minutes=TF_MINUTES[tf]) > _stamp(ctx.decision_time):
                continue
            if self._processed.get(tf) == newest:
                continue
            self._processed[tf] = newest
            event = _breakout(df, tf,
                              int(self.params.get("min_touches", 3)),
                              float(self.params.get("touch_tolerance_atr", 0.35)),
                              float(self.params.get("break_buffer_atr", 0.15)),
                              float(self.params.get("swing_prominence_atr", 0.20)))
            if event:
                self._events[tf] = event

    def _aligned(self, now: pd.Timestamp) -> dict[str, Any] | None:
        events = [self._events.get(tf) for tf in self.FRAME_SET]
        if any(e is None for e in events):
            return None
        directions = {e["direction"] for e in events}
        if len(directions) != 1:
            return None
        window = pd.Timedelta(hours=float(self.params.get("alignment_hours", 48)))
        times = [_stamp(e["confirmed_at"]) for e in events]
        if (max(times) > now or max(times)-min(times) > window
                or now-max(times) > pd.Timedelta(minutes=2)):
            # For combos, act only when the LAST required HTF break completes.
            return None
        signature = tuple((e["tf"], e["confirmed_at"], e["direction"]) for e in events)
        if signature == self._last_signature:
            return None
        self._last_signature = signature
        return {"direction": events[0]["direction"], "events": events,
                "trigger": max(events, key=lambda e: _stamp(e["confirmed_at"]))}

    def _opposite_exit(self, ctx):
        p = ctx.position
        if p is None or self.params.get("exit_mode", "fixed_r") != "opposite_break":
            return None
        if (getattr(p, "metadata", None) or {}).get("strategy_version") != "htf_trendline_breaks_v1":
            return None
        position_meta = getattr(p, "metadata", None) or {}
        entry_at = getattr(p, "entry_time", None) or position_meta.get("signal_time") or self._last_signal_time
        if entry_at is None:
            return None
        for tf in self.FRAME_SET:
            event = self._events.get(tf)
            if (event and event["direction"] != p.direction
                    and _stamp(event["confirmed_at"]) > _stamp(entry_at)):
                return ExitSignal(reason=f"opposite_{tf}_trendline_break")
        return None

    def _entry(self, ctx, signal: dict[str, Any]):
        bar = ctx.current_bar
        close = float(bar["close"])
        direction = signal["direction"]
        trigger = signal["trigger"]
        # Use the newest verified breakout line for structural stop reference.
        e_at = ctx.decision_time
        line_price = trigger["line"].value(e_at)
        atr = float(trigger["atr"])
        one_min = ctx.bars("1m", count=61)
        if len(one_min) < 15 or atr <= 0:
            return None
        recent = one_min.tail(60)
        if direction == "short":
            stop = max(float(recent["high"].max()),
                       float(trigger["bar_high"]), line_price+0.20*atr)
            risk_distance = stop-close
        else:
            stop = min(float(recent["low"].min()),
                       float(trigger["bar_low"]), line_price-0.20*atr)
            risk_distance = close-stop
        if risk_distance < 0.10*atr or risk_distance > 3.0*atr:
            return None
        # Freeze ALL lines behind the decision, not recompute from later data.
        drawings = [e["line"].drawing(e["broken_bar_start"],
                    role="trigger" if e is trigger else "confirmation")
                    for e in signal["events"]]
        metadata = {
            "strategy_version": "htf_trendline_breaks_v1",
            "signal_time": _iso(e_at),
            "timeframes": list(self.FRAME_SET),
            "entry_mode": self.params.get("entry_mode", "immediate"),
            "exit_mode": self.params.get("exit_mode", "fixed_r"),
            "line_schema_version": 1,
            "chart_drawings": drawings,
            "confirmation_events": [{
                "timeframe": e["tf"], "direction": e["direction"],
                "confirmed_at": e["confirmed_at"],
                "line_price_at_break": round(e["line_at_break"], 8),
            } for e in signal["events"]],
            "line_selection": "independent_pivot_triple_touch_no_lookahead_v1",
            "stop_rule": "break_bar_or_recent_1m_extreme_and_trendline_ATR_buffer",
        }
        mode = str(self.params.get("exit_mode", "fixed_r"))
        return EntrySignal(
            direction=direction, stop_loss=float(stop),
            target_r=float(self.params.get("target_r", 2.0)) if mode == "fixed_r" else None,
            reason=f"htf_trendline_{'_'.join(self.FRAME_SET)}_{direction}",
            metadata=metadata,
        )

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            return None
        self._scan(ctx)
        if ctx.position is not None:
            self._pending = None
            return self._opposite_exit(ctx)
        now = _stamp(ctx.decision_time)
        aligned = self._aligned(now)
        mode = str(self.params.get("entry_mode", "immediate"))
        if aligned:
            if mode == "retest_1m":
                self._pending = {"signal": aligned, "created": now,
                                 "bars": 0}
            else:
                if str(self.params.get("direction", "both")) in {"both", aligned["direction"]}:
                    self._last_signal_time = now
                    return self._entry(ctx, aligned)
        if mode != "retest_1m" or self._pending is None:
            return None
        pending = self._pending
        pending["bars"] += 1
        if pending["bars"] > int(self.params.get("retest_timeout_bars", 120)):
            self._pending = None
            return None
        if pending["bars"] <= 1:  # cannot retest in the breakout bar
            return None
        signal = pending["signal"]
        trigger = signal["trigger"]
        price_on_line = trigger["line"].value(now)
        tolerance = 0.20*trigger["atr"]
        bar = ctx.current_bar
        if signal["direction"] == "short":
            retest = (float(bar["high"]) >= price_on_line-tolerance
                      and float(bar["close"]) < price_on_line)
        else:
            retest = (float(bar["low"]) <= price_on_line+tolerance
                      and float(bar["close"]) > price_on_line)
        if not retest:
            return None
        self._pending = None
        if str(self.params.get("direction", "both")) not in {"both", signal["direction"]}:
            return None
        return self._entry(ctx, signal)


def _spec(key: str, title: str, frames: tuple[str, ...]) -> StrategySpec:
    return StrategySpec(
        key=key, name=title,
        description="Confirmed 3+ pivot HTF trendline close-break. "
                    "Multi-TF variants require same-direction breaks within alignment window; "
                    "1m only for execution or optional retest.",
        category="Trendline research",
        timeframes=("1m", *frames),
        defaults={"direction": "both", "entry_mode": "immediate",
                  "exit_mode": "fixed_r", "target_r": 2.0,
                  "min_touches": 3, "touch_tolerance_atr": 0.35,
                  "break_buffer_atr": 0.15, "swing_prominence_atr": 0.20,
                  "alignment_hours": 48,
                  "retest_timeout_bars": 120},
        parameters=(
            ParameterSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
            ParameterSpec("entry_mode", "Entry", "choice", "immediate", choices=("immediate", "retest_1m")),
            ParameterSpec("exit_mode", "Exit", "choice", "fixed_r", choices=("fixed_r", "opposite_break")),
            ParameterSpec("target_r", "Fixed R target", "float", 2.0, 0.5, 6.0, 0.5),
            ParameterSpec("min_touches", "Minimum touches", "int", 3, 3, 5, 1),
            ParameterSpec("touch_tolerance_atr", "Touch tolerance (ATR)", "float", 0.35, 0.1, 0.7, 0.05),
            ParameterSpec("break_buffer_atr", "Close beyond line (ATR)", "float", 0.15, 0.05, 0.6, 0.05),
            ParameterSpec("swing_prominence_atr", "Swing prominence (ATR)", "float", 0.20, 0.0, 0.8, 0.05),
            ParameterSpec("alignment_hours", "Confirmation window (hours)", "int", 48, 4, 120, 4),
            ParameterSpec("retest_timeout_bars", "1m retest expiry (bars)", "int", 120, 15, 480, 15),
        ),
        risk_management={
            "Scope": "15m+ trendlines only, 1m for fills/retest",
            "Pivots": "Two bars left/right; 0.20 ATR prominence; confirmed after right bar closes",
            "Touches": "Independent pivot touches at least four HTF bars apart; >=3",
            "Break": "Completed HTF candle closes >=0.15 ATR beyond line",
            "Combination": "All chosen TF lines break in same direction within 48h",
            "Stop": "Break candle/last 60 1m extrema, plus 0.2 HTF ATR line buffer",
            "Exit": "2R fixed target or opposite HTF trendline break (next 1m open)",
            "Charts": "chart_drawings in signal/trade metadata; UI needs overlay adapter",
        },
        source_file="backend/app/backtesting/strategies/htf_trendline_breaks_v1.py",
    )


@strategy_registry.register
class HTFTrendline15m(_TrendlineBase):
    FRAME_SET = ("15m",)
    spec = _spec("htf_tl_v1_15m", "TL01 · 15m break", FRAME_SET)


@strategy_registry.register
class HTFTrendline30m(_TrendlineBase):
    FRAME_SET = ("30m",)
    spec = _spec("htf_tl_v1_30m", "TL02 · 30m break", FRAME_SET)


@strategy_registry.register
class HTFTrendline1h(_TrendlineBase):
    FRAME_SET = ("1h",)
    spec = _spec("htf_tl_v1_1h", "TL03 · 1h break", FRAME_SET)


@strategy_registry.register
class HTFTrendline4h(_TrendlineBase):
    FRAME_SET = ("4h",)
    spec = _spec("htf_tl_v1_4h", "TL04 · 4h break", FRAME_SET)


@strategy_registry.register
class HTFTrendline15m1h(_TrendlineBase):
    FRAME_SET = ("15m", "1h")
    spec = _spec("htf_tl_v1_15m_1h", "TL05 · 15m + 1h agreement", FRAME_SET)


@strategy_registry.register
class HTFTrendline15m4h(_TrendlineBase):
    FRAME_SET = ("15m", "4h")
    spec = _spec("htf_tl_v1_15m_4h", "TL06 · 15m + 4h agreement", FRAME_SET)


@strategy_registry.register
class HTFTrendline1h4h(_TrendlineBase):
    FRAME_SET = ("1h", "4h")
    spec = _spec("htf_tl_v1_1h_4h", "TL07 · 1h + 4h agreement", FRAME_SET)


@strategy_registry.register
class HTFTrendline15m1h4h(_TrendlineBase):
    FRAME_SET = ("15m", "1h", "4h")
    spec = _spec("htf_tl_v1_15m_1h_4h", "TL08 · 15m + 1h + 4h agreement", FRAME_SET)
