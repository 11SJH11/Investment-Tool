#!/usr/bin/env python3
r"""
Ledger VWAP confluence discovery study v2 (research only, optimized).

Why v2 exists
-------------
The first broad confluence script rebuilt pivots/BOS/FVG/sweep state for every
trade. On multi-year runs that can take a very long time. This version builds
causal event indexes once per run, then each saved trade mostly performs bounded
lookups against those indexes.

Run from the Ledger backend directory, for example:

    .\.venv\Scripts\python.exe tools\vwap_confluence_research_v2.py \
        --run-id 182 179 181

Recommended first study:
    182 = D6 2020-01-01 -> 2023-09-02
    179 = D6 2023-10-01 -> 2025-12-31
    181 = D6 2026-04-01 -> 2026-10-02

This tool is deliberately diagnostic-only:
- no strategy files are modified;
- no backtests are rerun;
- ledger.db is read only;
- no provider data is fetched;
- no generated rule is promoted;
- all market-state features are reconstructed no later than the saved entry
  signal time.

Important statistical warning
-----------------------------
The output contains many interpretations/variants. They are for hypothesis
formation, not for selecting the best historical PF. Any promising idea must be
implemented as one conceptual strategy change and rerun through Ledger's full
engine because max-trades/day and replacement/path effects can reverse a static
subgroup result.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = Path(__file__).resolve().parent
for _p in (BACKEND_DIR, TOOLS_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from app.backtesting.context import completion_indexes
from app.core.config import get_settings
from app.services.chart_data import prepare_chart_bars
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.database import Database
from app.storage.market_store import MarketStore
from vwap_trade_feature_research import (
    candle_overlap_ratio,
    confirmation_features,
    derive_namespace,
    efficiency_ratio,
    get_signal_time,
    mean_true_range_bps,
    parse_utc,
    signed_efficiency_trade_relative,
    vwap_crossings,
)

NY = "America/New_York"
RTH_OPEN = 9 * 60 + 30
RTH_CLOSE = 16 * 60
PREMARKET_OPEN = 4 * 60
MINUTES_PER_RTH = RTH_CLOSE - RTH_OPEN

SWING_STRENGTHS = (1, 2, 3, 5)
LOOKBACK_MINUTES = (5, 15, 30, 60)
CONTEXT_WINDOWS = (5, 10, 20, 30, 60)
TIMEFRAMES = ("1m", "5m", "15m")
OR_WINDOWS = (5, 15, 30)
EQUAL_TOLS_BPS = (2.0, 5.0, 10.0)
RECLAIM_HORIZONS = (0, 1, 3, 5)

# Only the most recent confirmed levels are used for a same-session sweep probe.
# This is both causal and much more defensible than allowing a very old pivot to
# dominate a current setup forever.
RECENT_SWING_LEVELS_PER_SIDE = 6
EQUAL_CLUSTER_SOURCE_PIVOTS = 14


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_ns(value: Any) -> int:
    return int(parse_utc(value).value)


def minutes_between(a: pd.Timestamp | None, b: pd.Timestamp | None) -> float:
    if a is None or b is None:
        return np.nan
    return float((b - a).total_seconds() / 60.0)


def distance_bps(price: float, level: Any) -> float:
    level_f = finite(level)
    if level_f is None or price <= 0:
        return np.nan
    return (price - level_f) / price * 10_000.0


def duration_label(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


class Progress:
    def __init__(self, total: int, label: str, every: int = 25):
        self.total = max(1, int(total))
        self.label = label
        self.every = max(1, int(every))
        self.started = time.perf_counter()
        self.last_print = self.started

    def update(self, completed: int, *, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and completed < self.total and completed % self.every != 0 and now - self.last_print < 3.0:
            return
        elapsed = now - self.started
        rate = completed / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - completed)
        eta = remaining / rate if rate > 0 else float("inf")
        pct = completed / self.total * 100.0
        eta_text = duration_label(eta) if math.isfinite(eta) else "--:--"
        print(
            f"  {self.label}: {completed:,}/{self.total:,} ({pct:5.1f}%) | "
            f"elapsed {duration_label(elapsed)} | ETA {eta_text} | {rate:,.1f} trades/s",
            flush=True,
        )
        self.last_print = now


class TimedStage:
    def __init__(self, label: str):
        self.label = label
        self.started = 0.0

    def __enter__(self):
        print(f"  {self.label}...", flush=True)
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.perf_counter() - self.started
        if exc is None:
            print(f"    done in {duration_label(elapsed)}", flush=True)
        else:
            print(f"    FAILED after {duration_label(elapsed)}: {exc}", flush=True)
        return False


def _normalise_raw(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    frame["available_at"] = frame["timestamp"] + pd.Timedelta(minutes=1)
    local = frame["timestamp"].dt.tz_convert(NY)
    minute = local.dt.hour * 60 + local.dt.minute
    frame["session_date"] = local.dt.strftime("%Y-%m-%d")
    frame["local_minute"] = minute
    frame["session_minute"] = minute - RTH_OPEN
    frame["is_rth"] = (minute >= RTH_OPEN) & (minute < RTH_CLOSE)
    frame["is_premarket"] = (minute >= PREMARKET_OPEN) & (minute < RTH_OPEN)
    previous = frame["close"].shift(1)
    frame["tr"] = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["tr_bps"] = np.where(frame["close"] > 0, frame["tr"] / frame["close"] * 10_000.0, np.nan)
    return frame


def load_frames(
    store: MarketStore,
    namespace: str,
    symbol: str,
    run: dict[str, Any],
    history_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = (pd.Timestamp(run["start_date"]) - pd.Timedelta(days=history_days)).tz_localize(NY).tz_convert("UTC")
    end = (pd.Timestamp(run["end_date"]) + pd.Timedelta(days=2)).tz_localize(NY).tz_convert("UTC")
    raw = store.read_bars(namespace, symbol, "1m", start=start.isoformat(), end=end.isoformat())
    if raw.empty:
        raise RuntimeError(
            f"No cached 1m bars for {symbol} in {namespace!r}. "
            "This research tool never fetches provider data."
        )
    raw = _normalise_raw(raw)

    base = raw.loc[raw["is_rth"], ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    rth, _ = prepare_chart_bars(base, "1m", "regular", session_profile="us_equity")
    rth["timestamp"] = pd.to_datetime(rth["timestamp"], utc=True)
    rth["available_at"] = completion_indexes({"1m": rth})["1m"]
    local = rth["timestamp"].dt.tz_convert(NY)
    rth["session_date"] = local.dt.strftime("%Y-%m-%d")
    rth["local_minute"] = local.dt.hour * 60 + local.dt.minute
    rth["session_minute"] = rth["local_minute"] - RTH_OPEN
    rth["hlc3"] = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    rth["pv"] = rth["hlc3"] * rth["volume"]
    grouped = rth.groupby("session_date", sort=False)
    rth["cum_volume"] = grouped["volume"].cumsum()
    rth["cum_pv"] = grouped["pv"].cumsum()
    rth["vwap"] = np.where(rth["cum_volume"] > 0, rth["cum_pv"] / rth["cum_volume"], np.nan)
    previous = rth["close"].shift(1)
    rth["tr"] = pd.concat(
        [
            rth["high"] - rth["low"],
            (rth["high"] - previous).abs(),
            (rth["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    rth["tr_bps"] = np.where(rth["close"] > 0, rth["tr"] / rth["close"] * 10_000.0, np.nan)
    return raw.reset_index(drop=True), rth.reset_index(drop=True)


@dataclass
class Sessions:
    rth: pd.DataFrame
    raw: pd.DataFrame

    def __post_init__(self) -> None:
        self.rth_by = {
            str(key): group.sort_values("timestamp").reset_index(drop=True)
            for key, group in self.rth.groupby("session_date", sort=True)
        }
        self.raw_by = {
            str(key): group.sort_values("timestamp").reset_index(drop=True)
            for key, group in self.raw.groupby("session_date", sort=True)
        }
        self.dates = sorted(self.rth_by)
        self.pos = {date: index for index, date in enumerate(self.dates)}

    def prior_dates(self, date: str, n: int) -> list[str]:
        index = self.pos.get(date)
        if index is None:
            return []
        return self.dates[max(0, index - n):index]


@dataclass(frozen=True)
class Pivot:
    side: str
    price: float
    occurred_at: pd.Timestamp
    confirmed_at: pd.Timestamp
    session_pos: int


@dataclass(frozen=True)
class BreakEvent:
    side: str
    time: pd.Timestamp
    level: float
    magnitude_bps: float
    magnitude_tr: float
    session_pos: int


@dataclass(frozen=True)
class GapEvent:
    side: str
    created: pd.Timestamp
    size_bps: float
    lower: float
    upper: float
    session_pos: int
    touch_time: pd.Timestamp | None
    full_time: pd.Timestamp | None


class PivotSeries:
    """Sorted confirmed pivots with O(log n) causal prefix lookup."""

    def __init__(self, pivots: Iterable[Pivot]):
        ordered = sorted(pivots, key=lambda p: (p.confirmed_at, p.occurred_at, p.side))
        self.by_side: dict[str, list[Pivot]] = {}
        self.times: dict[str, list[int]] = {}
        for side in ("high", "low"):
            values = [p for p in ordered if p.side == side]
            self.by_side[side] = values
            self.times[side] = [int(p.confirmed_at.value) for p in values]

    def recent(
        self,
        side: str,
        signal: pd.Timestamp,
        *,
        min_session_pos: int,
        max_session_pos: int,
        n: int,
    ) -> list[Pivot]:
        values = self.by_side.get(side, [])
        times = self.times.get(side, [])
        index = bisect.bisect_right(times, int(signal.value)) - 1
        found: list[Pivot] = []
        while index >= 0 and len(found) < n:
            pivot = values[index]
            if pivot.session_pos < min_session_pos:
                break
            if pivot.session_pos <= max_session_pos:
                found.append(pivot)
            index -= 1
        found.reverse()
        return found


class BreakSeries:
    def __init__(self, events: Iterable[BreakEvent]):
        ordered = sorted(events, key=lambda e: e.time)
        self.by_side: dict[str, list[BreakEvent]] = {}
        self.times: dict[str, list[int]] = {}
        for side in ("bullish", "bearish"):
            values = [event for event in ordered if event.side == side]
            self.by_side[side] = values
            self.times[side] = [int(event.time.value) for event in values]

    def latest(
        self,
        side: str,
        signal: pd.Timestamp,
        *,
        min_session_pos: int,
        max_session_pos: int,
    ) -> BreakEvent | None:
        values = self.by_side.get(side, [])
        times = self.times.get(side, [])
        index = bisect.bisect_right(times, int(signal.value)) - 1
        while index >= 0:
            event = values[index]
            if event.session_pos < min_session_pos:
                return None
            if event.session_pos <= max_session_pos:
                return event
            index -= 1
        return None


class GapSeries:
    def __init__(self, gaps: Iterable[GapEvent]):
        ordered = sorted(gaps, key=lambda g: g.created)
        self.by_side: dict[str, list[GapEvent]] = {}
        self.times: dict[str, list[int]] = {}
        for side in ("bullish", "bearish"):
            values = [gap for gap in ordered if gap.side == side]
            self.by_side[side] = values
            self.times[side] = [int(gap.created.value) for gap in values]

    def latest(
        self,
        side: str,
        signal: pd.Timestamp,
        *,
        min_session_pos: int,
        max_session_pos: int,
    ) -> GapEvent | None:
        values = self.by_side.get(side, [])
        times = self.times.get(side, [])
        index = bisect.bisect_right(times, int(signal.value)) - 1
        while index >= 0:
            gap = values[index]
            if gap.session_pos < min_session_pos:
                return None
            if gap.session_pos <= max_session_pos:
                return gap
            index -= 1
        return None

    def recent_any(
        self,
        side: str,
        signal: pd.Timestamp,
        *,
        min_session_pos: int,
        max_session_pos: int,
        within_minutes: int,
        minimum_bps: float,
    ) -> bool:
        values = self.by_side.get(side, [])
        times = self.times.get(side, [])
        index = bisect.bisect_right(times, int(signal.value)) - 1
        floor = signal - pd.Timedelta(minutes=within_minutes)
        while index >= 0:
            gap = values[index]
            if gap.created < floor or gap.session_pos < min_session_pos:
                return False
            if gap.session_pos <= max_session_pos and gap.size_bps >= minimum_bps:
                return True
            index -= 1
        return False


def aggregate_timeframe(rth: pd.DataFrame, timeframe: str, session_pos: dict[str, int]) -> pd.DataFrame:
    if timeframe == "1m":
        bars = rth[["timestamp", "available_at", "open", "high", "low", "close", "volume", "session_date", "session_minute"]].copy()
    else:
        base = rth[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        bars, _ = prepare_chart_bars(base, timeframe, "regular", session_profile="us_equity")
        if bars.empty:
            return bars
        bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
        bars["available_at"] = completion_indexes({timeframe: bars})[timeframe]
        local = bars["timestamp"].dt.tz_convert(NY)
        bars["session_date"] = local.dt.strftime("%Y-%m-%d")
        bars["session_minute"] = local.dt.hour * 60 + local.dt.minute - RTH_OPEN
    bars["session_pos"] = bars["session_date"].map(session_pos).fillna(-1).astype(int)
    previous = bars["close"].shift(1)
    bars["tr"] = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - previous).abs(),
            (bars["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    bars["tr_bps"] = np.where(bars["close"] > 0, bars["tr"] / bars["close"] * 10_000.0, np.nan)
    return bars.reset_index(drop=True)


def detect_pivots(bars: pd.DataFrame, strength: int) -> list[Pivot]:
    """Strict unique pivots, never spanning an RTH session boundary."""
    if len(bars) < strength * 2 + 1:
        return []
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    positions = bars["session_pos"].to_numpy(dtype=int)
    timestamps = bars["timestamp"].tolist()
    available = bars["available_at"].tolist()
    output: list[Pivot] = []
    for index in range(strength, len(bars) - strength):
        left = index - strength
        right = index + strength + 1
        if np.any(positions[left:right] != positions[index]):
            continue
        high_window = highs[left:right]
        low_window = lows[left:right]
        if highs[index] == np.max(high_window) and int(np.sum(high_window == highs[index])) == 1:
            output.append(
                Pivot(
                    "high",
                    float(highs[index]),
                    pd.Timestamp(timestamps[index]),
                    pd.Timestamp(available[index + strength]),
                    int(positions[index]),
                )
            )
        if lows[index] == np.min(low_window) and int(np.sum(low_window == lows[index])) == 1:
            output.append(
                Pivot(
                    "low",
                    float(lows[index]),
                    pd.Timestamp(timestamps[index]),
                    pd.Timestamp(available[index + strength]),
                    int(positions[index]),
                )
            )
    return output


def detect_breaks(
    bars: pd.DataFrame,
    pivot_series: PivotSeries,
    *,
    wick: bool,
) -> list[BreakEvent]:
    """Break the latest already-confirmed same/previous-session swing.

    A pivot can emit at most one event. This is a cleaner causal BOS variant than
    repeatedly breaking every historical pivot.
    """
    pivots_all = sorted(
        pivot_series.by_side["high"] + pivot_series.by_side["low"],
        key=lambda p: (p.confirmed_at, p.occurred_at),
    )
    pivot_i = 0
    latest: dict[str, Pivot | None] = {"high": None, "low": None}
    consumed: set[tuple[str, int]] = set()
    output: list[BreakEvent] = []

    for row in bars.itertuples(index=False):
        available_at = pd.Timestamp(row.available_at)
        while pivot_i < len(pivots_all) and pivots_all[pivot_i].confirmed_at <= available_at:
            pivot = pivots_all[pivot_i]
            latest[pivot.side] = pivot
            pivot_i += 1

        for pivot_side, event_side in (("high", "bullish"), ("low", "bearish")):
            pivot = latest[pivot_side]
            if pivot is None or pivot.confirmed_at >= available_at:
                continue
            identity = (pivot_side, int(pivot.occurred_at.value))
            if identity in consumed:
                continue
            if wick:
                crossed = float(row.high) > pivot.price if pivot_side == "high" else float(row.low) < pivot.price
                move_price = float(row.high) if pivot_side == "high" else float(row.low)
            else:
                crossed = float(row.close) > pivot.price if pivot_side == "high" else float(row.close) < pivot.price
                move_price = float(row.close)
            if not crossed:
                continue
            magnitude = abs(move_price - pivot.price) / pivot.price * 10_000.0 if pivot.price > 0 else np.nan
            tr = finite(row.tr)
            output.append(
                BreakEvent(
                    event_side,
                    available_at,
                    pivot.price,
                    magnitude,
                    abs(move_price - pivot.price) / tr if tr and tr > 0 else np.nan,
                    int(row.session_pos),
                )
            )
            consumed.add(identity)
    return output


def detect_gaps(bars: pd.DataFrame) -> list[GapEvent]:
    """Same-session three-candle FVGs plus first touch/full-fill timestamps."""
    if len(bars) < 3:
        return []
    output: list[GapEvent] = []
    # Work session-by-session so neither detection nor mitigation crosses overnight.
    for session_pos, session in bars.groupby("session_pos", sort=False):
        session = session.reset_index(drop=True)
        highs = session["high"].to_numpy(dtype=float)
        lows = session["low"].to_numpy(dtype=float)
        closes = session["close"].to_numpy(dtype=float)
        available = [pd.Timestamp(x) for x in session["available_at"]]
        n = len(session)
        for index in range(2, n):
            if lows[index] > highs[index - 2]:
                lower, upper, side = highs[index - 2], lows[index], "bullish"
            elif highs[index] < lows[index - 2]:
                lower, upper, side = highs[index], lows[index - 2], "bearish"
            else:
                continue
            base = closes[index - 2]
            size = (upper - lower) / base * 10_000.0 if base > 0 else np.nan
            touch_time = None
            full_time = None
            for future in range(index + 1, n):
                if side == "bullish":
                    touched = lows[future] <= upper
                    full = lows[future] <= lower
                else:
                    touched = highs[future] >= lower
                    full = highs[future] >= upper
                if touch_time is None and touched:
                    touch_time = available[future]
                if full_time is None and full:
                    full_time = available[future]
                if touch_time is not None and full_time is not None:
                    break
            output.append(
                GapEvent(
                    side,
                    available[index],
                    float(size),
                    float(lower),
                    float(upper),
                    int(session_pos),
                    touch_time,
                    full_time,
                )
            )
    return output


@dataclass
class ConceptIndex:
    timeframes: dict[str, pd.DataFrame]
    pivots: dict[tuple[str, int], PivotSeries]
    bos: dict[tuple[str, int], BreakSeries]
    wick: dict[tuple[str, int], BreakSeries]
    gaps: dict[str, GapSeries]


def build_concept_index(rth: pd.DataFrame, sessions: Sessions) -> ConceptIndex:
    timeframes: dict[str, pd.DataFrame] = {}
    pivot_indexes: dict[tuple[str, int], PivotSeries] = {}
    bos_indexes: dict[tuple[str, int], BreakSeries] = {}
    wick_indexes: dict[tuple[str, int], BreakSeries] = {}
    gap_indexes: dict[str, GapSeries] = {}

    for timeframe in TIMEFRAMES:
        with TimedStage(f"Precompute {timeframe} bars / pivots / BOS / FVG"):
            bars = aggregate_timeframe(rth, timeframe, sessions.pos)
            timeframes[timeframe] = bars
            gap_indexes[timeframe] = GapSeries(detect_gaps(bars))
            for strength in SWING_STRENGTHS:
                series = PivotSeries(detect_pivots(bars, strength))
                pivot_indexes[(timeframe, strength)] = series
                bos_indexes[(timeframe, strength)] = BreakSeries(detect_breaks(bars, series, wick=False))
                wick_indexes[(timeframe, strength)] = BreakSeries(detect_breaks(bars, series, wick=True))

    return ConceptIndex(timeframes, pivot_indexes, bos_indexes, wick_indexes, gap_indexes)


class TimeOfDayMatrix:
    """Fast same-time-of-day baselines from prior sessions only."""

    def __init__(self, sessions: Sessions, widths: tuple[int, ...] = (1, 5, 15)):
        self.sessions = sessions
        count = len(sessions.dates)
        shape = (count, MINUTES_PER_RTH)
        volume = np.full(shape, np.nan, dtype=float)
        tr = np.full(shape, np.nan, dtype=float)
        high = np.full(shape, np.nan, dtype=float)
        low = np.full(shape, np.nan, dtype=float)
        close = np.full(shape, np.nan, dtype=float)

        for session_pos, date in enumerate(sessions.dates):
            frame = sessions.rth_by[date]
            for row in frame.itertuples(index=False):
                minute = int(row.session_minute)
                if 0 <= minute < MINUTES_PER_RTH:
                    volume[session_pos, minute] = finite(row.volume) or 0.0
                    tr[session_pos, minute] = finite(row.tr_bps) if finite(row.tr_bps) is not None else np.nan
                    high[session_pos, minute] = float(row.high)
                    low[session_pos, minute] = float(row.low)
                    close[session_pos, minute] = float(row.close)

        self.values: dict[int, dict[str, np.ndarray]] = {}
        for width in widths:
            vol_out = np.full(shape, np.nan, dtype=float)
            tr_out = np.full(shape, np.nan, dtype=float)
            range_out = np.full(shape, np.nan, dtype=float)
            for pos in range(count):
                for minute in range(width - 1, MINUTES_PER_RTH):
                    start = minute - width + 1
                    v = volume[pos, start:minute + 1]
                    t = tr[pos, start:minute + 1]
                    h = high[pos, start:minute + 1]
                    l = low[pos, start:minute + 1]
                    c = close[pos, minute]
                    if np.isfinite(v).all():
                        vol_out[pos, minute] = float(np.sum(v))
                    if np.isfinite(t).all():
                        tr_out[pos, minute] = float(np.mean(t))
                    if np.isfinite(h).all() and np.isfinite(l).all() and math.isfinite(c) and c > 0:
                        range_out[pos, minute] = (float(np.max(h)) - float(np.min(l))) / c * 10_000.0
            self.values[width] = {"volume": vol_out, "tr": tr_out, "range": range_out}

    def lookup(self, session_pos: int, minute: int, width: int, prior_sessions: int) -> dict[str, float]:
        output = {
            "history_sessions": 0,
            "relative_volume": np.nan,
            "relative_volatility": np.nan,
            "volatility_percentile": np.nan,
            "range_percentile": np.nan,
        }
        if width not in self.values or session_pos < 0 or minute < 0 or minute >= MINUTES_PER_RTH:
            return output
        current = self.values[width]
        start = max(0, session_pos - prior_sessions)
        prior_vol = current["volume"][start:session_pos, minute]
        prior_tr = current["tr"][start:session_pos, minute]
        prior_range = current["range"][start:session_pos, minute]
        mask = np.isfinite(prior_vol) & np.isfinite(prior_tr) & np.isfinite(prior_range)
        prior_vol = prior_vol[mask]
        prior_tr = prior_tr[mask]
        prior_range = prior_range[mask]
        output["history_sessions"] = int(len(prior_vol))
        if len(prior_vol) == 0:
            return output
        this_vol = current["volume"][session_pos, minute]
        this_tr = current["tr"][session_pos, minute]
        this_range = current["range"][session_pos, minute]
        med_vol = float(np.median(prior_vol))
        med_tr = float(np.median(prior_tr))
        if math.isfinite(this_vol) and med_vol > 0:
            output["relative_volume"] = float(this_vol / med_vol)
        if math.isfinite(this_tr) and med_tr > 0:
            output["relative_volatility"] = float(this_tr / med_tr)
        if math.isfinite(this_tr) and len(prior_tr) >= 10:
            output["volatility_percentile"] = float(np.mean(prior_tr <= this_tr))
        if math.isfinite(this_range) and len(prior_range) >= 10:
            output["range_percentile"] = float(np.mean(prior_range <= this_range))
        return output


def prior_levels(sessions: Sessions, date: str) -> dict[str, float]:
    dates = sessions.prior_dates(date, 5)
    output: dict[str, float] = {}
    if dates:
        last = sessions.rth_by[dates[-1]]
        output.update(
            pdh=float(last["high"].max()),
            pdl=float(last["low"].min()),
            pdc=float(last["close"].iloc[-1]),
        )
    else:
        output.update(pdh=np.nan, pdl=np.nan, pdc=np.nan)
    for count in (3, 5):
        use = dates[-count:]
        if use:
            combined = pd.concat([sessions.rth_by[d] for d in use], ignore_index=True)
            output[f"prior_{count}d_high"] = float(combined["high"].max())
            output[f"prior_{count}d_low"] = float(combined["low"].min())
        else:
            output[f"prior_{count}d_high"] = np.nan
            output[f"prior_{count}d_low"] = np.nan
    return output


def premarket_levels(sessions: Sessions, date: str, signal: pd.Timestamp) -> dict[str, Any]:
    frame = sessions.raw_by.get(date, pd.DataFrame())
    if frame.empty:
        return {"available": False, "pmh": np.nan, "pml": np.nan}
    pm = frame.loc[frame["is_premarket"] & (frame["available_at"] <= signal)]
    return {
        "available": not pm.empty,
        "pmh": float(pm["high"].max()) if not pm.empty else np.nan,
        "pml": float(pm["low"].min()) if not pm.empty else np.nan,
    }


def opening_range(prior: pd.DataFrame, minutes: int) -> tuple[float, float, bool]:
    frame = prior.loc[prior["session_minute"].between(0, minutes - 1)]
    if len(frame) < minutes:
        return np.nan, np.nan, False
    return float(frame["high"].max()), float(frame["low"].min()), True


def contextual(prior: pd.DataFrame, direction: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for minutes in CONTEXT_WINDOWS:
        frame = prior.tail(minutes)
        prefix = f"context.{minutes}m"
        if len(frame) < minutes:
            for key in ("efficiency", "trade_efficiency", "overlap", "vwap_crosses", "mean_tr_bps", "range_bps", "alternations"):
                output[f"{prefix}.{key}"] = np.nan
            continue
        output[f"{prefix}.efficiency"] = efficiency_ratio(frame["close"])
        output[f"{prefix}.trade_efficiency"] = signed_efficiency_trade_relative(frame["close"], direction)
        output[f"{prefix}.overlap"] = candle_overlap_ratio(frame)
        output[f"{prefix}.vwap_crosses"] = vwap_crossings(frame)
        output[f"{prefix}.mean_tr_bps"] = mean_true_range_bps(frame)
        close = float(frame["close"].iloc[-1])
        output[f"{prefix}.range_bps"] = (
            (float(frame["high"].max()) - float(frame["low"].min())) / close * 10_000.0
            if close > 0 else np.nan
        )
        signs = np.sign((frame["close"] - frame["open"]).to_numpy(dtype=float))
        signs = signs[signs != 0]
        output[f"{prefix}.alternations"] = float(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0.0

    recent5 = prior.tail(5)
    previous20 = prior.iloc[max(0, len(prior) - 25):max(0, len(prior) - 5)]
    recent10 = prior.tail(10)
    previous30 = prior.iloc[max(0, len(prior) - 40):max(0, len(prior) - 10)]
    output["compression.expansion_tr_ratio_5_vs_prev20"] = (
        float(recent5["tr_bps"].mean() / previous20["tr_bps"].mean())
        if len(recent5) == 5 and len(previous20) == 20 and previous20["tr_bps"].mean() > 0
        else np.nan
    )
    output["compression.tr_ratio_10_vs_prev30"] = (
        float(recent10["tr_bps"].mean() / previous30["tr_bps"].mean())
        if len(recent10) == 10 and len(previous30) == 30 and previous30["tr_bps"].mean() > 0
        else np.nan
    )
    components = [
        (finite(output.get("context.20m.efficiency")), lambda x: x <= 0.35),
        (finite(output.get("context.20m.overlap")), lambda x: x >= 0.55),
        (finite(output.get("context.20m.vwap_crosses")), lambda x: x >= 2),
        (finite(output.get("compression.tr_ratio_10_vs_prev30")), lambda x: x <= 0.85),
    ]
    output["heuristic.accumulation_proxy_score_20m"] = (
        sum(int(test(value)) for value, test in components)
        if all(value is not None for value, _ in components)
        else np.nan
    )
    return output


def structure_state(highs: list[Pivot], lows: list[Pivot]) -> dict[str, Any]:
    high_state = "unknown"
    low_state = "unknown"
    if len(highs) >= 2:
        high_state = "HH" if highs[-1].price > highs[-2].price else "LH" if highs[-1].price < highs[-2].price else "EH"
    if len(lows) >= 2:
        low_state = "HL" if lows[-1].price > lows[-2].price else "LL" if lows[-1].price < lows[-2].price else "EL"
    if high_state == "HH" and low_state == "HL":
        state = "bullish"
    elif high_state == "LH" and low_state == "LL":
        state = "bearish"
    elif high_state != "unknown" or low_state != "unknown":
        state = "mixed"
    else:
        state = "unknown"
    return {
        "high": high_state,
        "low": low_state,
        "state": state,
        "last_high": highs[-1].price if highs else np.nan,
        "last_low": lows[-1].price if lows else np.nan,
    }


def sweep_variants(
    frame: pd.DataFrame,
    level: Any,
    side: str,
    *,
    start_minute: int | None = None,
) -> dict[int, dict[str, Any] | None]:
    """Latest wick-through + reclaim for all configured horizons in one pass."""
    level_f = finite(level)
    result = {horizon: None for horizon in RECLAIM_HORIZONS}
    if level_f is None or level_f <= 0 or frame.empty:
        return result
    use = frame
    if start_minute is not None:
        use = use.loc[use["session_minute"] >= start_minute]
    if use.empty:
        return result
    use = use.reset_index(drop=True)
    highs = use["high"].to_numpy(dtype=float)
    lows = use["low"].to_numpy(dtype=float)
    closes = use["close"].to_numpy(dtype=float)
    available = [pd.Timestamp(x) for x in use["available_at"]]
    breach_indexes = np.flatnonzero(lows < level_f) if side == "low" else np.flatnonzero(highs > level_f)
    for index in breach_indexes:
        max_end = min(len(use) - 1, index + max(RECLAIM_HORIZONS))
        reclaimed_at = None
        for future in range(index, max_end + 1):
            reclaimed = closes[future] > level_f if side == "low" else closes[future] < level_f
            if reclaimed:
                reclaimed_at = future
                break
        if reclaimed_at is None:
            continue
        bars_to_reclaim = reclaimed_at - index
        extreme = float(np.min(lows[index:reclaimed_at + 1])) if side == "low" else float(np.max(highs[index:reclaimed_at + 1]))
        depth = (level_f - extreme) / level_f * 10_000.0 if side == "low" else (extreme - level_f) / level_f * 10_000.0
        event = {
            "time": available[reclaimed_at],
            "depth_bps": float(depth),
            "level": float(level_f),
            "reclaim_bars": int(bars_to_reclaim),
        }
        for horizon in RECLAIM_HORIZONS:
            if bars_to_reclaim <= horizon:
                result[horizon] = event
    return result


def latest_level_take(frame: pd.DataFrame, level: Any, side: str, *, start_minute: int | None = None) -> pd.Timestamp | None:
    level_f = finite(level)
    if level_f is None or frame.empty:
        return None
    use = frame
    if start_minute is not None:
        use = use.loc[use["session_minute"] >= start_minute]
    if use.empty:
        return None
    mask = use["high"] > level_f if side == "high" else use["low"] < level_f
    hits = use.loc[mask]
    return pd.Timestamp(hits.iloc[-1]["available_at"]) if not hits.empty else None


def equal_clusters(pivots: list[Pivot], tolerance_bps: float) -> list[dict[str, Any]]:
    groups: list[list[Pivot]] = []
    for pivot in pivots:
        placed = False
        for group in groups:
            centre = float(np.mean([item.price for item in group]))
            if centre > 0 and abs(pivot.price / centre - 1.0) * 10_000.0 <= tolerance_bps:
                group.append(pivot)
                placed = True
                break
        if not placed:
            groups.append([pivot])
    return [
        {
            "price": float(np.mean([item.price for item in group])),
            "confirmed_at": max(item.confirmed_at for item in group),
            "count": len(group),
        }
        for group in groups
        if len(group) >= 2
    ]


def room_to_level(price: float, direction: str, levels: dict[str, Any]) -> tuple[str, float]:
    candidates: list[tuple[str, float]] = []
    for name, value in levels.items():
        level = finite(value)
        if level is None:
            continue
        if (direction == "long" and level > price) or (direction == "short" and level < price):
            candidates.append((name, level))
    if not candidates:
        return "", np.nan
    name, level = min(candidates, key=lambda item: abs(item[1] - price))
    return name, abs(level - price) / price * 10_000.0


def gap_features(
    series: GapSeries,
    signal: pd.Timestamp,
    direction: str,
    *,
    min_session_pos: int,
    max_session_pos: int,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    wanted = "bullish" if direction == "long" else "bearish"
    opposite = "bearish" if wanted == "bullish" else "bullish"
    for label, side in (("directional", wanted), ("opposing", opposite)):
        gap = series.latest(side, signal, min_session_pos=min_session_pos, max_session_pos=max_session_pos)
        prefix = f"fvg.{label}"
        output[f"{prefix}.exists"] = bool(gap)
        output[f"{prefix}.age_minutes"] = minutes_between(gap.created, signal) if gap else np.nan
        output[f"{prefix}.size_bps"] = gap.size_bps if gap else np.nan
        output[f"{prefix}.unmitigated_touch"] = (
            bool(gap.touch_time is None or gap.touch_time > signal) if gap else np.nan
        )
        output[f"{prefix}.unfilled_full"] = (
            bool(gap.full_time is None or gap.full_time > signal) if gap else np.nan
        )
        for minimum in (0.0, 2.0, 5.0):
            output[f"{prefix}.recent30_ge_{minimum:g}bps"] = series.recent_any(
                side,
                signal,
                min_session_pos=min_session_pos,
                max_session_pos=max_session_pos,
                within_minutes=30,
                minimum_bps=minimum,
            )
    return output


def outcome(trade: dict[str, Any], direction: str) -> dict[str, Any]:
    entry = finite(trade.get("entry_price"))
    exit_price = finite(trade.get("exit_price"))
    r_multiple = finite(trade.get("r_multiple"))
    net_pnl = finite(trade.get("net_pnl"))
    gross_bps = (
        (exit_price / entry - 1.0) * 10_000.0 * (1 if direction == "long" else -1)
        if entry and exit_price and entry > 0
        else np.nan
    )
    if net_pnl is not None:
        winner = net_pnl > 0
    elif r_multiple is not None:
        winner = r_multiple > 0
    else:
        winner = bool(finite(gross_bps) is not None and gross_bps > 0)
    try:
        duration = (parse_utc(trade["exit_time"]) - parse_utc(trade["entry_time"])).total_seconds() / 60.0
    except Exception:
        duration = np.nan
    reason = str(trade.get("exit_reason") or "").lower()
    session_close = any(token in reason for token in ("session_close", "end_of_session", "market_close", "eod"))
    return {
        "outcome.r_multiple": r_multiple if r_multiple is not None else np.nan,
        "outcome.net_pnl": net_pnl if net_pnl is not None else np.nan,
        "outcome.gross_price_bps": gross_bps,
        "outcome.winner": bool(winner),
        "outcome.duration_minutes": duration,
        "outcome.fast_loss_5m": bool(not winner and finite(duration) is not None and duration <= 5),
        "outcome.fast_loss_10m": bool(not winner and finite(duration) is not None and duration <= 10),
        "outcome.fast_loss_20m": bool(not winner and finite(duration) is not None and duration <= 20),
        "outcome.fast_loss_30m": bool(not winner and finite(duration) is not None and duration <= 30),
        "outcome.session_close_exit": bool(session_close),
    }


def feature_row(
    run_id: int,
    trade_index: int,
    trade: dict[str, Any],
    all_rth: pd.DataFrame,
    sessions: Sessions,
    concepts: ConceptIndex,
    tod: TimeOfDayMatrix,
    structure_sessions: int,
    tod_sessions: int,
) -> dict[str, Any]:
    direction = str(trade.get("direction") or "").lower()
    row: dict[str, Any] = {
        "run_id": run_id,
        "trade_number": trade_index + 1,
        "direction": direction,
        "entry_time": trade.get("entry_time"),
        "exit_time": trade.get("exit_time"),
        "exit_reason": trade.get("exit_reason"),
    }
    if direction not in {"long", "short"}:
        row["research.warning"] = "unsupported_direction"
        return row

    row.update(outcome(trade, direction))
    signal, signal_source = get_signal_time(trade, all_rth)
    row["signal_time_source"] = signal_source
    row["signal_time_utc"] = signal.isoformat() if signal is not None else ""
    if signal is None:
        row["research.warning"] = "missing_signal_time"
        return row

    date = signal.tz_convert(NY).strftime("%Y-%m-%d")
    session_pos = sessions.pos.get(date)
    row["session_date"] = date
    if session_pos is None:
        row["research.warning"] = "signal_session_missing_from_cache"
        return row

    current = sessions.rth_by.get(date, pd.DataFrame())
    prior = current.loc[current["available_at"] <= signal].copy()
    if prior.empty:
        row["research.warning"] = "no_completed_rth_bars"
        return row

    current_bar = prior.iloc[-1]
    price = float(current_bar["close"])
    minute = int(current_bar["session_minute"])
    row["minutes_since_open"] = minute + 1
    row["signal_close"] = price
    row["signal_vwap"] = finite(current_bar.get("vwap"))
    row.update(confirmation_features(trade, all_rth, direction, signal))
    row.update(contextual(prior, direction))

    # Session/opening state.
    levels = prior_levels(sessions, date)
    pm = premarket_levels(sessions, date, signal)
    levels.update(pmh=pm["pmh"], pml=pm["pml"])
    row["liquidity.premarket_available"] = bool(pm["available"])
    for name, value in levels.items():
        row[f"level.{name}"] = value
        row[f"location.distance_to_{name}_bps_signed"] = distance_bps(price, value)

    session_open = float(prior["open"].iloc[0])
    session_high = float(prior["high"].max())
    session_low = float(prior["low"].min())
    session_range = session_high - session_low
    row["session.open_to_signal_bps"] = (price / session_open - 1.0) * 10_000.0 if session_open > 0 else np.nan
    row["session.open_to_signal_trade_relative_bps"] = row["session.open_to_signal_bps"] * (1 if direction == "long" else -1)
    row["session.range_bps_so_far"] = session_range / price * 10_000.0 if price > 0 else np.nan
    row["session.position_in_range"] = (price - session_low) / session_range if session_range > 0 else np.nan
    row["session.retracement_from_adverse_extreme"] = (
        row["session.position_in_range"] if direction == "long" else 1.0 - row["session.position_in_range"]
        if finite(row["session.position_in_range"]) is not None
        else np.nan
    )
    pdc = finite(levels.get("pdc"))
    row["session.gap_from_pdc_bps"] = (session_open / pdc - 1.0) * 10_000.0 if pdc and pdc > 0 else np.nan
    row["session.gap_from_pdc_trade_relative_bps"] = (
        row["session.gap_from_pdc_bps"] * (1 if direction == "long" else -1)
        if finite(row["session.gap_from_pdc_bps"]) is not None
        else np.nan
    )
    for window in (5, 15, 30):
        opening = prior.loc[prior["session_minute"].between(0, window - 1)]
        drive = (
            (float(opening["close"].iloc[-1]) / float(opening["open"].iloc[0]) - 1.0) * 10_000.0
            if len(opening) >= window
            else np.nan
        )
        row[f"session.opening_drive_{window}m_bps"] = drive
        row[f"session.opening_drive_{window}m_trade_relative_bps"] = (
            drive * (1 if direction == "long" else -1) if finite(drive) is not None else np.nan
        )

    for name in ("pdh", "pdl", "pmh", "pml", "prior_3d_high", "prior_3d_low", "prior_5d_high", "prior_5d_low"):
        signed = distance_bps(price, levels.get(name))
        absolute = abs(signed) if finite(signed) is not None else np.nan
        for threshold in (5, 10, 20):
            row[f"location.near_{name}_{threshold}bps"] = bool(finite(absolute) is not None and absolute <= threshold)

    for window in OR_WINDOWS:
        high, low, formed = opening_range(prior, window)
        levels[f"or{window}h"] = high
        levels[f"or{window}l"] = low
        row[f"level.or{window}h"] = high
        row[f"level.or{window}l"] = low
        row[f"level.or{window}_formed"] = formed

    # Static known-liquidity levels: one bounded same-session scan per level, with
    # all reclaim horizons derived at once.
    adverse_side = "low" if direction == "long" else "high"
    trade_side = "high" if direction == "long" else "low"
    adverse_names = (
        ["pdl", "prior_3d_low", "prior_5d_low", "pml"] + [f"or{x}l" for x in OR_WINDOWS]
        if direction == "long"
        else ["pdh", "prior_3d_high", "prior_5d_high", "pmh"] + [f"or{x}h" for x in OR_WINDOWS]
    )
    trade_names = (
        ["pdh", "prior_3d_high", "prior_5d_high", "pmh"] + [f"or{x}h" for x in OR_WINDOWS]
        if direction == "long"
        else ["pdl", "prior_3d_low", "prior_5d_low", "pml"] + [f"or{x}l" for x in OR_WINDOWS]
    )
    latest_static: dict[str, Any] | None = None
    for name in adverse_names:
        start_minute = int(name[2:-1]) if name.startswith("or") else None
        variants_for_level = sweep_variants(prior, levels.get(name), adverse_side, start_minute=start_minute)
        for reclaim, event in variants_for_level.items():
            prefix = f"liquidity.{name}.adverse_sweep_reclaim_{reclaim}"
            row[f"{prefix}.exists"] = bool(event)
            row[f"{prefix}.minutes_ago"] = minutes_between(event["time"], signal) if event else np.nan
            row[f"{prefix}.depth_bps"] = event["depth_bps"] if event else np.nan
            for lookback in LOOKBACK_MINUTES:
                row[f"{prefix}.within_{lookback}m"] = bool(
                    event and 0 <= minutes_between(event["time"], signal) <= lookback
                )
            if reclaim == 3 and event and (latest_static is None or event["time"] > latest_static["time"]):
                latest_static = {**event, "name": name}

    for name in trade_names:
        start_minute = int(name[2:-1]) if name.startswith("or") else None
        event_time = latest_level_take(prior, levels.get(name), trade_side, start_minute=start_minute)
        row[f"liquidity.{name}.taken_trade_direction"] = bool(event_time)
        row[f"liquidity.{name}.taken_minutes_ago"] = minutes_between(event_time, signal) if event_time else np.nan

    # Causal structure/BOS/FVG lookups from precomputed indexes.
    wanted = "bullish" if direction == "long" else "bearish"
    opposite = "bearish" if wanted == "bullish" else "bullish"
    rolling_min_pos = max(0, session_pos - structure_sessions)
    states_s2: dict[str, str] = {}
    canonical_pivots_adverse: list[Pivot] = []
    canonical_bos: BreakEvent | None = None
    canonical_structure: dict[str, Any] | None = None

    for scope_name, min_pos in (("current", session_pos), ("rolling", rolling_min_pos)):
        for timeframe in TIMEFRAMES:
            for strength in SWING_STRENGTHS:
                pivot_series = concepts.pivots[(timeframe, strength)]
                highs = pivot_series.recent(
                    "high", signal, min_session_pos=min_pos, max_session_pos=session_pos, n=max(2, RECENT_SWING_LEVELS_PER_SIDE)
                )
                lows = pivot_series.recent(
                    "low", signal, min_session_pos=min_pos, max_session_pos=session_pos, n=max(2, RECENT_SWING_LEVELS_PER_SIDE)
                )
                structure = structure_state(highs, lows)
                prefix = f"structure.{scope_name}.{timeframe}.s{strength}"
                row[f"{prefix}.high_state"] = structure["high"]
                row[f"{prefix}.low_state"] = structure["low"]
                row[f"{prefix}.state"] = structure["state"]
                row[f"{prefix}.aligned"] = structure["state"] == wanted
                row[f"{prefix}.opposing"] = structure["state"] == opposite

                bos = concepts.bos[(timeframe, strength)].latest(
                    wanted, signal, min_session_pos=min_pos, max_session_pos=session_pos
                )
                opposing_bos = concepts.bos[(timeframe, strength)].latest(
                    opposite, signal, min_session_pos=min_pos, max_session_pos=session_pos
                )
                wick = concepts.wick[(timeframe, strength)].latest(
                    wanted, signal, min_session_pos=min_pos, max_session_pos=session_pos
                )
                bos_prefix = f"bos.{scope_name}.{timeframe}.s{strength}"
                row[f"{bos_prefix}.directional_exists"] = bool(bos)
                row[f"{bos_prefix}.directional_minutes_ago"] = minutes_between(bos.time, signal) if bos else np.nan
                row[f"{bos_prefix}.directional_magnitude_bps"] = bos.magnitude_bps if bos else np.nan
                row[f"{bos_prefix}.directional_magnitude_tr"] = bos.magnitude_tr if bos else np.nan
                row[f"{bos_prefix}.opposing_exists"] = bool(opposing_bos)
                row[f"{bos_prefix}.opposing_minutes_ago"] = minutes_between(opposing_bos.time, signal) if opposing_bos else np.nan
                row[f"{bos_prefix}.wick_break_directional_exists"] = bool(wick)
                row[f"{bos_prefix}.wick_break_directional_minutes_ago"] = minutes_between(wick.time, signal) if wick else np.nan
                for lookback in LOOKBACK_MINUTES:
                    row[f"{bos_prefix}.directional_within_{lookback}m"] = bool(
                        bos and 0 <= minutes_between(bos.time, signal) <= lookback
                    )
                row[f"{bos_prefix}.mss_proxy"] = bool(bos and structure["state"] in {opposite, "mixed"})

                if scope_name == "rolling" and strength == 2:
                    states_s2[timeframe] = structure["state"]
                    if timeframe == "1m":
                        canonical_structure = structure
                        canonical_bos = bos
                        canonical_pivots_adverse = lows if adverse_side == "low" else highs

            for key, value in gap_features(
                concepts.gaps[timeframe],
                signal,
                direction,
                min_session_pos=min_pos,
                max_session_pos=session_pos,
            ).items():
                row[f"{key}.{scope_name}.{timeframe}"] = value

    row["structure.rolling.s2.aligned_timeframes"] = sum(states_s2.get(tf) == wanted for tf in TIMEFRAMES)
    row["structure.rolling.s2.all_1m5m15m_aligned"] = all(states_s2.get(tf) == wanted for tf in TIMEFRAMES)

    # Swing-liquidity variants: only recent confirmed pivots, and only same-session
    # breaches/reclaims are scanned. This keeps the concept interpretable and fast.
    latest_swing: dict[str, Any] | None = None
    for strength in SWING_STRENGTHS:
        pivot_series = concepts.pivots[("1m", strength)]
        side_pivots = pivot_series.recent(
            adverse_side,
            signal,
            min_session_pos=rolling_min_pos,
            max_session_pos=session_pos,
            n=RECENT_SWING_LEVELS_PER_SIDE,
        )
        by_horizon: dict[int, dict[str, Any] | None] = {h: None for h in RECLAIM_HORIZONS}
        for pivot in side_pivots:
            result = sweep_variants(prior, pivot.price, adverse_side)
            for horizon, event in result.items():
                if event and (by_horizon[horizon] is None or event["time"] > by_horizon[horizon]["time"]):
                    by_horizon[horizon] = {**event, "pivot_price": pivot.price, "pivot_confirmed_at": pivot.confirmed_at}
        for horizon, event in by_horizon.items():
            prefix = f"liquidity.swing_s{strength}.adverse_sweep_reclaim_{horizon}"
            row[f"{prefix}.exists"] = bool(event)
            row[f"{prefix}.minutes_ago"] = minutes_between(event["time"], signal) if event else np.nan
            row[f"{prefix}.depth_bps"] = event["depth_bps"] if event else np.nan
            for lookback in LOOKBACK_MINUTES:
                row[f"{prefix}.within_{lookback}m"] = bool(
                    event and 0 <= minutes_between(event["time"], signal) <= lookback
                )
            if strength == 2 and horizon == 3 and event:
                latest_swing = event

    # Equal highs/lows from recent confirmed pivots only; cluster formation itself
    # therefore cannot use a future pivot.
    recent_equal_source = canonical_pivots_adverse[-EQUAL_CLUSTER_SOURCE_PIVOTS:]
    for tolerance in EQUAL_TOLS_BPS:
        clusters = equal_clusters(recent_equal_source, tolerance)
        latest = None
        for cluster in clusters:
            if cluster["confirmed_at"] > signal:
                continue
            event = sweep_variants(prior, cluster["price"], adverse_side)[3]
            if event and (latest is None or event["time"] > latest["time"]):
                latest = event
        prefix = f"liquidity.equal_{adverse_side}s_tol_{tolerance:g}bps"
        row[f"{prefix}.cluster_count"] = len(clusters)
        row[f"{prefix}.sweep_exists"] = bool(latest)
        row[f"{prefix}.sweep_minutes_ago"] = minutes_between(latest["time"], signal) if latest else np.nan

    # Canonical sequence hypothesis = latest adverse liquidity sweep (static or s2)
    # followed by directional 1m s2 BOS, then the saved VWAP signal.
    sweep = latest_swing
    if latest_static and (sweep is None or latest_static["time"] > sweep["time"]):
        sweep = latest_static
    sweep_time = sweep["time"] if sweep else None
    bos_time = canonical_bos.time if canonical_bos else None
    row["sequence.sweep_exists"] = bool(sweep_time)
    row["sequence.bos_exists"] = bool(bos_time)
    row["sequence.sweep_then_bos"] = bool(sweep_time is not None and bos_time is not None and sweep_time < bos_time)
    row["sequence.bos_then_sweep"] = bool(sweep_time is not None and bos_time is not None and bos_time < sweep_time)
    row["sequence.sweep_to_bos_minutes"] = minutes_between(sweep_time, bos_time) if row["sequence.sweep_then_bos"] else np.nan
    row["sequence.sweep_to_signal_minutes"] = minutes_between(sweep_time, signal) if sweep_time else np.nan
    row["sequence.bos_to_signal_minutes"] = minutes_between(bos_time, signal) if bos_time else np.nan
    for lookback in (15, 30, 60):
        row[f"sequence.sweep_bos_signal_within_{lookback}m"] = bool(
            row["sequence.sweep_then_bos"]
            and row["sequence.sweep_to_signal_minutes"] <= lookback
            and row["sequence.bos_to_signal_minutes"] <= lookback
        )

    # Time-of-day normalized volume/volatility.
    for width in (1, 5, 15):
        stats = tod.lookup(session_pos, minute, width, tod_sessions)
        prefix = f"tod.{width}m"
        for key, value in stats.items():
            row[f"{prefix}.{key}"] = value

    canonical_structure = canonical_structure or {"last_high": np.nan, "last_low": np.nan}
    room_levels = {
        **levels,
        "last_swing_high_s2": canonical_structure.get("last_high", np.nan),
        "last_swing_low_s2": canonical_structure.get("last_low", np.nan),
    }
    name, room = room_to_level(price, direction, room_levels)
    row["location.next_opposing_level_name"] = name
    row["location.room_to_next_opposing_level_bps"] = room
    row["location.distance_to_last_swing_high_bps_signed"] = distance_bps(price, canonical_structure.get("last_high"))
    row["location.distance_to_last_swing_low_bps_signed"] = distance_bps(price, canonical_structure.get("last_low"))
    row["research.warning"] = ""
    return row


def profit_factor(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses > 0:
        return gains / losses
    return np.inf if gains > 0 else np.nan


def performance(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {
            "n": 0,
            "win_rate_pct": np.nan,
            "avg_r": np.nan,
            "pf_r": np.nan,
            "avg_gross_bps": np.nan,
            "fast_loss_10_pct": np.nan,
        }
    winners = df["outcome.winner"].astype(bool)
    r = pd.to_numeric(df["outcome.r_multiple"], errors="coerce")
    bps = pd.to_numeric(df["outcome.gross_price_bps"], errors="coerce")
    fast = df["outcome.fast_loss_10m"].astype(bool)
    return {
        "n": len(df),
        "win_rate_pct": float(winners.mean() * 100.0),
        "avg_r": float(r.mean()) if r.notna().any() else np.nan,
        "pf_r": profit_factor(r),
        "avg_gross_bps": float(bps.mean()) if bps.notna().any() else np.nan,
        "fast_loss_10_pct": float(fast.mean() * 100.0),
    }


def bool_mask(series: pd.Series) -> pd.Series:
    def convert(value: Any) -> bool:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if pd.isna(value):
            return False
        return str(value).strip().lower() in {"true", "1"}
    return series.map(convert).astype(bool)


def variant_specs(df: pd.DataFrame):
    specs: list[tuple[str, pd.Series, pd.Series, str]] = []
    boolean_prefixes = ("liquidity.", "bos.", "structure.", "sequence.", "fvg.", "location.near_")
    for column in df.columns:
        if not column.startswith(boolean_prefixes):
            continue
        non_missing = df[column].dropna()
        if non_missing.empty:
            continue
        values = set(non_missing.astype(str).str.lower().unique())
        if not values.issubset({"true", "false", "1", "0"}):
            continue
        available = df[column].notna()
        present = bool_mask(df[column])
        family = column.split(".")[0]
        specs.append((f"{column} == true", present, available, family))
        specs.append((f"{column} == false", ~present, available, family))

    for column in [c for c in df.columns if c.startswith("structure.") and c.endswith(".state")]:
        available = df[column].notna() & ~df[column].astype(str).eq("unknown")
        for state in ("bullish", "bearish", "mixed"):
            specs.append((f"{column} == {state}", df[column].astype(str).eq(state), available, "structure_state"))

    for width in (1, 5, 15):
        column = f"tod.{width}m.volatility_percentile"
        if column in df:
            x = pd.to_numeric(df[column], errors="coerce")
            available = x.notna()
            specs.extend(
                [
                    (f"{column}:low_q1", x < 0.25, available, "volatility"),
                    (f"{column}:middle", (x >= 0.25) & (x < 0.75), available, "volatility"),
                    (f"{column}:high_q4", x >= 0.75, available, "volatility"),
                    (f"{column}:top10", x >= 0.90, available, "volatility"),
                ]
            )
        column = f"tod.{width}m.relative_volume"
        if column in df:
            x = pd.to_numeric(df[column], errors="coerce")
            available = x.notna()
            specs.extend(
                [
                    (f"{column}:lt_.75", x < 0.75, available, "volume"),
                    (f"{column}:.75_1", (x >= 0.75) & (x < 1.0), available, "volume"),
                    (f"{column}:1_1.5", (x >= 1.0) & (x < 1.5), available, "volume"),
                    (f"{column}:ge_1.5", x >= 1.5, available, "volume"),
                ]
            )

    for minutes in CONTEXT_WINDOWS:
        column = f"context.{minutes}m.efficiency"
        if column in df:
            x = pd.to_numeric(df[column], errors="coerce")
            available = x.notna()
            specs.extend(
                [
                    (f"{column}:lt_.25", x < 0.25, available, "efficiency"),
                    (f"{column}:.25_.5", (x >= 0.25) & (x < 0.5), available, "efficiency"),
                    (f"{column}:.5_.75", (x >= 0.5) & (x < 0.75), available, "efficiency"),
                    (f"{column}:ge_.75", x >= 0.75, available, "efficiency"),
                ]
            )

    column = "heuristic.accumulation_proxy_score_20m"
    if column in df:
        x = pd.to_numeric(df[column], errors="coerce")
        available = x.notna()
        for threshold in (2, 3, 4):
            specs.append((f"{column} >= {threshold}", x >= threshold, available, "accumulation_proxy"))

    column = "location.room_to_next_opposing_level_bps"
    if column in df:
        x = pd.to_numeric(df[column], errors="coerce")
        available = x.notna()
        for threshold in (5, 10, 20, 40):
            specs.append((f"{column} >= {threshold}", x >= threshold, available, "room"))

    return specs


def top_winner_retention(valid: pd.DataFrame, selected_mask: pd.Series) -> float:
    winners = valid.loc[valid["outcome.winner"].astype(bool)].copy()
    if len(winners) < 10:
        return np.nan
    score = pd.to_numeric(winners["outcome.r_multiple"], errors="coerce")
    if not score.notna().any():
        score = pd.to_numeric(winners["outcome.gross_price_bps"], errors="coerce")
    winners = winners.assign(_score=score).dropna(subset=["_score"])
    if len(winners) < 10:
        return np.nan
    cutoff = winners["_score"].quantile(0.90)
    top = winners.loc[winners["_score"] >= cutoff]
    if top.empty:
        return np.nan
    selected_aligned = selected_mask.reindex(top.index, fill_value=False)
    return float(selected_aligned.mean() * 100.0)


def build_variant_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [("ALL", df)]
    scopes.extend((f"RUN_{int(run_id)}", group) for run_id, group in df.groupby("run_id"))
    scopes.extend((f"ALL_{direction.upper()}", df.loc[df["direction"] == direction]) for direction in ("long", "short"))

    for name, mask, available, family in variant_specs(df):
        for scope, group in scopes:
            selected_global = mask.reindex(group.index, fill_value=False)
            available_global = available.reindex(group.index, fill_value=False)
            valid = group.loc[available_global]
            selected = group.loc[available_global & selected_global]
            other = group.loc[available_global & ~selected_global]
            selected_perf = performance(selected)
            other_perf = performance(other)
            rows.append(
                {
                    "variant": name,
                    "family": family,
                    "scope": scope,
                    "available_n": len(valid),
                    **{f"selected_{key}": value for key, value in selected_perf.items()},
                    **{f"other_{key}": value for key, value in other_perf.items()},
                    "coverage_pct": len(selected) / len(valid) * 100.0 if len(valid) else np.nan,
                    "delta_avg_r": (
                        selected_perf["avg_r"] - other_perf["avg_r"]
                        if finite(selected_perf["avg_r"]) is not None and finite(other_perf["avg_r"]) is not None
                        else np.nan
                    ),
                    "delta_avg_gross_bps": (
                        selected_perf["avg_gross_bps"] - other_perf["avg_gross_bps"]
                        if finite(selected_perf["avg_gross_bps"]) is not None and finite(other_perf["avg_gross_bps"]) is not None
                        else np.nan
                    ),
                    "delta_fast_loss_10_pct": (
                        selected_perf["fast_loss_10_pct"] - other_perf["fast_loss_10_pct"]
                        if finite(selected_perf["fast_loss_10_pct"]) is not None and finite(other_perf["fast_loss_10_pct"]) is not None
                        else np.nan
                    ),
                    "top_winner_retention_pct": top_winner_retention(valid, selected_global),
                }
            )
    return pd.DataFrame(rows)


def cross_run_stability(variant_summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if variant_summary.empty:
        return pd.DataFrame()
    source = variant_summary[
        variant_summary["scope"].str.match(r"^RUN_\d+$", na=False)
    ]
    for (name, family), group in source.groupby(["variant", "family"]):
        usable = group[
            (pd.to_numeric(group["selected_n"], errors="coerce") >= 20)
            & pd.to_numeric(group["delta_avg_r"], errors="coerce").notna()
        ]
        delta = pd.to_numeric(usable["delta_avg_r"], errors="coerce")
        fast = pd.to_numeric(usable["delta_fast_loss_10_pct"], errors="coerce")
        retention = pd.to_numeric(usable["top_winner_retention_pct"], errors="coerce")
        rows.append(
            {
                "variant": name,
                "family": family,
                "runs_with_n_ge_20": len(usable),
                "positive_delta_runs": int((delta > 0).sum()),
                "negative_delta_runs": int((delta < 0).sum()),
                "mean_delta_avg_r": float(delta.mean()) if len(delta) else np.nan,
                "mean_delta_fast_loss_10_pct": float(fast.mean()) if len(fast) else np.nan,
                "mean_top_winner_retention_pct": float(retention.mean()) if retention.notna().any() else np.nan,
                "same_positive_direction_all_usable": bool(len(usable) >= 2 and (delta > 0).all()),
            }
        )
    return pd.DataFrame(rows)


def hypothesis_candidates(variant_summary: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    if variant_summary.empty or stability.empty:
        return pd.DataFrame()
    combined = variant_summary.loc[variant_summary["scope"] == "ALL"].merge(
        stability, on=["variant", "family"], how="left"
    )
    n = pd.to_numeric(combined["selected_n"], errors="coerce")
    coverage = pd.to_numeric(combined["coverage_pct"], errors="coerce")
    delta = pd.to_numeric(combined["delta_avg_r"], errors="coerce")
    fast = pd.to_numeric(combined["delta_fast_loss_10_pct"], errors="coerce")
    retention = pd.to_numeric(combined["top_winner_retention_pct"], errors="coerce")
    runs = pd.to_numeric(combined["runs_with_n_ge_20"], errors="coerce").fillna(0)
    positive = pd.to_numeric(combined["positive_delta_runs"], errors="coerce").fillna(0)

    combined["triage_score"] = (
        0.20 * np.clip(n / 100.0, 0, 1)
        + 0.30 * np.where(runs > 0, positive / runs, 0)
        + 0.20 * np.tanh(delta.fillna(0) / 0.10)
        + 0.15 * np.tanh((-fast.fillna(0)) / 10.0)
        + 0.15 * np.clip(retention.fillna(0) / 100.0, 0, 1)
        + np.where(coverage < 10, -0.75, np.where(coverage < 20, -0.25, 0))
    )
    combined["diagnostic_verdict"] = np.select(
        [
            (n < 20) | (coverage < 5),
            (runs >= 2) & (positive == runs) & (delta > 0),
            (runs >= 2) & (positive <= runs / 2),
        ],
        ["SMALL_SAMPLE", "PROMISING_STABLE_DIAGNOSTIC", "WEAK_OR_INCONSISTENT"],
        default="INTERESTING_NEEDS_REVIEW",
    )
    combined["warning"] = "Diagnostic subgroup only; full-engine rerun required for path/replacement effects."
    return combined.sort_values(["triage_score", "selected_n"], ascending=[False, False]).reset_index(drop=True)


def continuous_quantiles(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    columns = [
        column
        for column in df.columns
        if column.startswith(("context.", "compression.", "tod.", "location.", "session."))
        and pd.api.types.is_numeric_dtype(df[column])
    ]
    for column in columns:
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(values) < 80 or values.nunique() < 8:
            continue
        try:
            quartiles = pd.qcut(values, 4, duplicates="drop")
        except ValueError:
            continue
        for interval in quartiles.cat.categories:
            index = quartiles.index[quartiles == interval]
            rows.append({"feature": column, "bin": str(interval), **performance(df.loc[index])})
    return pd.DataFrame(rows)


def write_report(
    path: Path,
    df: pd.DataFrame,
    candidates: pd.DataFrame,
    metadata: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    lines = [
        "# VWAP confluence discovery report — optimized v2",
        "",
        "## Contract",
        "",
        "- Diagnostic only; no strategy rule was changed.",
        "- Features use information available no later than the saved entry signal.",
        "- Saved outcomes are immutable; market context is reconstructed from the current cache.",
        "- Static subgroup results are **not** equivalent to a strategy rerun because of M3/path/replacement effects.",
        "- Broad feature discovery creates multiple-testing risk. Prefer repeated cross-period relationships with a coherent market explanation.",
        "- v2 precomputes causal pivots/BOS/FVG event indexes once per run; per-trade work is limited to causal lookups and bounded same-session liquidity scans.",
        "",
        "## Runs",
        "",
    ]
    for item in metadata:
        lines.append(
            f"- **Run {item['run_id']}**: {item['start_date']} → {item['end_date']}; "
            f"{item['trades']} trades; `{item['strategy_key']}`; "
            f"{item['cached_prior_rth_sessions']} cached sessions before run start; "
            f"runtime {item.get('runtime_seconds', 0):.1f}s."
        )
    lines += [
        "",
        "## Coverage",
        "",
        f"- Combined trades: **{len(df):,}**",
        f"- Feature columns: **{len(df.columns):,}**",
        f"- Runs: **{df['run_id'].nunique()}**",
        "",
    ]
    if warnings:
        lines += ["### Warnings", ""] + [f"- {warning}" for warning in warnings] + [""]
    lines += [
        "## Highest-priority diagnostic hypotheses",
        "",
        "These are triage candidates, **not validated trading rules**.",
        "",
        "| # | Variant | Family | N | Coverage | Δ avg R | Top-winner retention | Positive runs | Verdict |",
        "|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    if candidates.empty:
        lines.append("| - | No ranked candidates | - | - | - | - | - | - | - |")
    else:
        for index, item in candidates.head(40).iterrows():
            delta = finite(item.get("delta_avg_r"))
            coverage = finite(item.get("coverage_pct"))
            retention = finite(item.get("top_winner_retention_pct"))
            selected_n = int(item.get("selected_n") or 0)
            positive = int(item.get("positive_delta_runs") or 0)
            runs = int(item.get("runs_with_n_ge_20") or 0)
            lines.append(
                f"| {index + 1} | `{item['variant']}` | {item['family']} | {selected_n} | "
                f"{coverage:.1f}% | {delta:+.3f} | {retention:.1f}% | {positive}/{runs} | {item['diagnostic_verdict']} |"
                if delta is not None and coverage is not None and retention is not None
                else f"| {index + 1} | `{item['variant']}` | {item['family']} | {selected_n} | n/a | n/a | n/a | {positive}/{runs} | {item['diagnostic_verdict']} |"
            )
    lines += [
        "",
        "## Definitions used",
        "",
        "- **BOS:** first completed close through the latest already-confirmed strict swing level; one BOS per pivot.",
        "- **Wick break:** first wick through that same already-confirmed swing; kept separate from close-BOS.",
        "- **Sweep/reclaim:** wick beyond an already-known level and close back inside on the same bar or within the declared 1/3/5-bar horizon.",
        "- **Swing sweep:** same-session sweep of one of the most recent confirmed swing levels from the current + previous structure-session window.",
        "- **MSS proxy:** directional BOS while current two-sided structure is opposing or mixed. This is a research proxy, not a canonical CHOCH claim.",
        "- **Structure:** strict unique 1/1, 2/2, 3/3 and 5/5 pivot variants on 1m/5m/15m; current-session and rolling prior-session views.",
        "- **FVG:** same-session three-candle gap with first touch and full-fill times tracked causally.",
        "- **Accumulation proxy:** explicitly heuristic combination of low 20m efficiency, high candle overlap, repeated VWAP crossings and volatility contraction. Inspect components separately.",
        "",
        "## What to do next",
        "",
        "1. Inspect `cross_run_stability.csv` before looking at the highest combined subgroup result.",
        "2. Compare `top_winners.csv`, `top_losers.csv` and `fast_losses.csv` for mechanism and winner preservation.",
        "3. Prefer a small number of coherent hypotheses such as `sweep → BOS → VWAP` over stacking correlated filters.",
        "4. Implement one conceptual change at a time.",
        "5. Rerun the **full Ledger engine** and inspect removed plus newly introduced replacement trades before accepting anything.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def process_run(
    repo: BacktestRunRepository,
    store: MarketStore,
    run_id: int,
    *,
    history_days: int,
    structure_sessions: int,
    tod_sessions: int,
    progress_every: int,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    started = time.perf_counter()
    run = repo.get(run_id)
    result = run.get("result") or {}
    trades = result.get("trades") or []
    symbols = result.get("symbols") or run.get("symbols") or []
    primary = result.get("primary_timeframe") or run.get("primary_timeframe")
    strategy = result.get("strategy") or {}

    if primary != "1m":
        raise RuntimeError(f"Run {run_id} uses {primary!r}; expected 1m.")
    if len(symbols) != 1 or str(symbols[0]).upper() != "QQQ":
        raise RuntimeError(f"Run {run_id} symbols are {symbols!r}; this study currently expects QQQ.")
    if not trades:
        raise RuntimeError(f"Run {run_id} has no saved trades.")

    print("=" * 86, flush=True)
    print(
        f"Run {run_id}: {run.get('name') or strategy.get('name') or strategy.get('key')} | "
        f"{run.get('start_date')} -> {run.get('end_date')} | {len(trades):,} trades",
        flush=True,
    )

    namespace = derive_namespace(run, "QQQ")
    with TimedStage(f"Load cached QQQ 1m history ({history_days} prior calendar days)"):
        raw, rth = load_frames(store, namespace, "QQQ", run, history_days)
    sessions = Sessions(rth, raw)
    warm_sessions = [date for date in sessions.dates if date < str(run.get("start_date"))]
    print(
        f"    cache: {len(raw):,} raw 1m bars / {len(rth):,} RTH bars / "
        f"{len(sessions.dates):,} RTH sessions / {len(warm_sessions):,} prior sessions",
        flush=True,
    )

    with TimedStage("Build same-time-of-day 1m/5m/15m matrices"):
        tod = TimeOfDayMatrix(sessions)
    concepts = build_concept_index(rth, sessions)

    rows: list[dict[str, Any]] = []
    progress = Progress(len(trades), f"Run {run_id} trade features", every=progress_every)
    for index, trade in enumerate(trades):
        rows.append(
            feature_row(
                run_id,
                index,
                trade,
                rth,
                sessions,
                concepts,
                tod,
                structure_sessions,
                tod_sessions,
            )
        )
        progress.update(index + 1)
    progress.update(len(trades), force=True)
    df = pd.DataFrame(rows)

    warnings: list[str] = []
    if len(warm_sessions) < min(40, tod_sessions):
        warnings.append(
            f"Run {run_id}: only {len(warm_sessions)} cached RTH sessions precede the run; "
            "early time-of-day percentiles may be unavailable."
        )
    if not bool(raw["is_premarket"].any()):
        warnings.append(f"Run {run_id}: current cache contains no premarket bars; PMH/PML features are unavailable.")
    reconstructed = int((df.get("signal_time_source", pd.Series(dtype=str)) == "reconstructed_trade_review_fallback").sum())
    if reconstructed:
        warnings.append(
            f"Run {run_id}: {reconstructed} entry signals used the same legacy completed-bar fallback as Trade Review."
        )
    params = strategy.get("params") or (run.get("config") or {}).get("strategy_params") or {}
    d6 = finite(params.get("min_confirmation_displacement_bps"))
    if d6 is not None and not math.isclose(d6, 6.0, rel_tol=0, abs_tol=1e-9):
        warnings.append(
            f"Run {run_id}: min_confirmation_displacement_bps={d6:g}, not the frozen D6 value. "
            "Check that this is one of the intended final comparison runs."
        )

    runtime = time.perf_counter() - started
    metadata = {
        "run_id": run_id,
        "start_date": run.get("start_date"),
        "end_date": run.get("end_date"),
        "trades": len(trades),
        "strategy_key": strategy.get("key") or run.get("strategy_key"),
        "strategy_params": params,
        "namespace": namespace,
        "cache_first": str(raw["timestamp"].min()),
        "cache_last": str(raw["timestamp"].max()),
        "cached_prior_rth_sessions": len(warm_sessions),
        "runtime_seconds": runtime,
    }
    print(f"  Run {run_id} finished in {duration_label(runtime)}", flush=True)
    return df, metadata, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimized broad causal confluence discovery for saved VWAP runs.")
    parser.add_argument("--run-id", type=int, nargs="+", required=True, help="Final VWAP run IDs from different periods")
    parser.add_argument("--out-dir", type=Path, default=Path("research_output/vwap_confluence"))
    parser.add_argument(
        "--history-days",
        type=int,
        default=400,
        help="Calendar days loaded before each run. Default 400 gives comfortable room for the 60-session TOD baseline.",
    )
    parser.add_argument("--structure-sessions", type=int, default=5, help="Prior RTH sessions included in rolling structure/BOS context")
    parser.add_argument("--tod-sessions", type=int, default=60, help="Prior sessions for same-time-of-day volume/volatility baselines")
    parser.add_argument("--progress-every", type=int, default=25, help="Print trade progress at least every N trades")
    args = parser.parse_args()

    if args.history_days < 90:
        raise SystemExit("--history-days must be >= 90; 400 is recommended for the 60-session historical baseline")
    if not 1 <= args.structure_sessions <= 20:
        raise SystemExit("--structure-sessions must be 1..20")
    if not 10 <= args.tod_sessions <= 120:
        raise SystemExit("--tod-sessions must be 10..120")
    if args.progress_every < 1:
        raise SystemExit("--progress-every must be >= 1")

    settings = get_settings()
    repo = BacktestRunRepository(Database(settings.database_path))
    store = MarketStore(settings.market_data_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Ledger DB: {settings.database_path.resolve()}", flush=True)
    print(f"Market cache: {settings.market_data_dir.resolve()}", flush=True)
    print(f"Runs: {args.run_id}", flush=True)
    print(
        f"Research settings: history={args.history_days} calendar days, "
        f"rolling structure={args.structure_sessions} sessions, TOD baseline={args.tod_sessions} sessions",
        flush=True,
    )

    all_frames: list[pd.DataFrame] = []
    metadata: list[dict[str, Any]] = []
    warnings: list[str] = []
    overall_started = time.perf_counter()

    for run_id in args.run_id:
        frame, run_meta, run_warnings = process_run(
            repo,
            store,
            run_id,
            history_days=args.history_days,
            structure_sessions=args.structure_sessions,
            tod_sessions=args.tod_sessions,
            progress_every=args.progress_every,
        )
        all_frames.append(frame)
        metadata.append(run_meta)
        warnings.extend(run_warnings)
        output = args.out_dir / f"run-{run_id}-confluence-features.csv"
        frame.to_csv(output, index=False, encoding="utf-8")
        print(f"  Wrote {output} ({len(frame):,} rows / {len(frame.columns):,} columns)", flush=True)

    with TimedStage("Combine runs and score diagnostic variants"):
        combined = pd.concat(all_frames, ignore_index=True, sort=False)
        combined.to_csv(args.out_dir / "trade_features.csv", index=False, encoding="utf-8")
        variant_summary = build_variant_summary(combined)
        variant_summary.to_csv(args.out_dir / "variant_summary.csv", index=False, encoding="utf-8")
        quantiles = continuous_quantiles(combined)
        quantiles.to_csv(args.out_dir / "continuous_quantiles.csv", index=False, encoding="utf-8")
        stability = cross_run_stability(variant_summary)
        stability.to_csv(args.out_dir / "cross_run_stability.csv", index=False, encoding="utf-8")
        candidates = hypothesis_candidates(variant_summary, stability)
        candidates.to_csv(args.out_dir / "hypothesis_candidates.csv", index=False, encoding="utf-8")

    rank_column = (
        "outcome.r_multiple"
        if pd.to_numeric(combined["outcome.r_multiple"], errors="coerce").notna().any()
        else "outcome.gross_price_bps"
    )
    winners = combined.loc[combined["outcome.winner"].astype(bool)].sort_values(rank_column, ascending=False).head(50)
    losers = combined.loc[~combined["outcome.winner"].astype(bool)].sort_values(rank_column).head(50)
    fast_losses = combined.loc[combined["outcome.fast_loss_10m"].astype(bool)]
    winners.to_csv(args.out_dir / "top_winners.csv", index=False, encoding="utf-8")
    losers.to_csv(args.out_dir / "top_losers.csv", index=False, encoding="utf-8")
    fast_losses.to_csv(args.out_dir / "fast_losses.csv", index=False, encoding="utf-8")

    provenance = {
        "tool": "vwap_confluence_research_v2.py",
        "feature_version": "vwap-confluence-discovery-v2-precomputed",
        "run_ids": args.run_id,
        "history_days": args.history_days,
        "structure_sessions": args.structure_sessions,
        "tod_sessions": args.tod_sessions,
        "run_metadata": metadata,
        "warnings": warnings,
        "definitions": {
            "bos": "first completed close through latest already-confirmed strict swing; one event per pivot",
            "wick_break": "first wick through latest already-confirmed strict swing; separate from close-BOS",
            "sweep": "wick beyond known level + reclaim within declared bar horizon",
            "swing_sweep": f"same-session sweep of one of last {RECENT_SWING_LEVELS_PER_SIDE} confirmed levels per side",
            "swing_strengths": SWING_STRENGTHS,
            "lookback_minutes": LOOKBACK_MINUTES,
            "opening_ranges": OR_WINDOWS,
            "equal_level_tolerance_bps": EQUAL_TOLS_BPS,
            "history_note": "400 calendar days by default; TOD comparisons use up to 60 prior RTH sessions",
        },
        "warning": "Diagnostic subgroup analysis only; full-engine rerun required.",
    }
    (args.out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")
    write_report(args.out_dir / "report.md", combined, candidates, metadata, warnings)

    elapsed = time.perf_counter() - overall_started
    print("=" * 86, flush=True)
    print(f"DONE in {duration_label(elapsed)}", flush=True)
    print("Read these first:", flush=True)
    for name in (
        "report.md",
        "hypothesis_candidates.csv",
        "cross_run_stability.csv",
        "variant_summary.csv",
        "continuous_quantiles.csv",
        "top_winners.csv",
        "top_losers.csv",
        "fast_losses.csv",
        "trade_features.csv",
        "provenance.json",
    ):
        print(f"  {(args.out_dir / name).resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
