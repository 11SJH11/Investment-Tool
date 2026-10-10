#!/usr/bin/env python3
r"""
Ledger VWAP trade-entry research feature extractor.

This is a RESEARCH-ONLY tool:
- It does not modify strategies.
- It does not rerun backtests.
- It does not write to ledger.db.
- It reads immutable saved trades plus Ledger's current cached 1m QQQ bars.
- It reconstructs causal features available by each recorded entry signal time.

Run from the backend directory, for example:

    .\.venv\Scripts\python.exe tools\vwap_trade_feature_research.py --run-id 173 175

Outputs:
    research_output/run-173-entry-features.csv
    research_output/run-175-entry-features.csv

Important provenance note:
Saved trade facts are immutable snapshots, but the research features are reconstructed
from the CURRENT market-data cache. Provider revisions/cache refreshes can therefore
make reconstructed context differ slightly from the original historical input.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# Make `app` importable when this script is run directly from backend/tools or backend.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository
from app.storage.market_store import MarketStore
from app.services.chart_data import prepare_chart_bars
from app.backtesting.context import completion_indexes


NY = "America/New_York"
RTH_OPEN_MINUTE = 9 * 60 + 30
RTH_CLOSE_MINUTE = 16 * 60

EXPECTED_STRATEGY = "vwap_trend_entry_exit_distance_research_v4"
EXPECTED_PARAMS = {
    "entry_confirmation_bars": 3,
    "exit_confirmation_bars": 2,
    "max_entry_vwap_distance_bps": 25.0,
    "trend_timeframe": "1d",
    "trend_ema_length": 20,
}
EXPECTED_RUN_CONTROLS = {
    "max_trades_per_day": 3,
    "cooldown_minutes": 0,
}


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def safe_bps(new: float, base: float) -> float:
    if not (math.isfinite(new) and math.isfinite(base)) or base == 0:
        return np.nan
    return (new / base - 1.0) * 10_000.0


def rel(value: float, direction: str) -> float:
    if pd.isna(value):
        return np.nan
    return float(value) if direction == "long" else -float(value)


def direction_sign(direction: str) -> int:
    return 1 if direction == "long" else -1


def parse_utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def run_snapshot(repo: BacktestRunRepository, run_id: int) -> dict[str, Any]:
    return repo.get(run_id)


def print_run_check(run: dict[str, Any]) -> None:
    config = run.get("config") or {}
    result = run.get("result") or {}
    strategy = result.get("strategy") or {}
    params = strategy.get("params") or config.get("strategy_params") or {}
    metrics = result.get("metrics") or {}

    print()
    print("=" * 78)
    print(f"Run {run['id']}: {run.get('name') or strategy.get('name') or strategy.get('key')}")
    print(f"Period: {run.get('start_date')} -> {run.get('end_date')}")
    print(f"Strategy: {strategy.get('key') or run.get('strategy_key')}")
    print(f"Symbols: {result.get('symbols') or run.get('symbols')}")
    print(f"Timeframe/session: {result.get('primary_timeframe')} / {result.get('session')}")
    print(
        "Metrics snapshot: "
        f"trades={metrics.get('trades')} "
        f"win_rate={metrics.get('win_rate_pct')} "
        f"PF={metrics.get('profit_factor_r')} "
        f"return={metrics.get('return_pct')}% "
        f"maxDD={metrics.get('max_drawdown_pct')}%"
    )

    checks: list[tuple[str, Any, Any, bool]] = []
    actual_key = strategy.get("key") or run.get("strategy_key")
    checks.append(("strategy key", actual_key, EXPECTED_STRATEGY, actual_key == EXPECTED_STRATEGY))
    for key, expected in EXPECTED_PARAMS.items():
        actual = params.get(key)
        ok = str(actual) == str(expected)
        if isinstance(expected, float):
            try:
                ok = math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-9)
            except (TypeError, ValueError):
                ok = False
        checks.append((f"strategy_params.{key}", actual, expected, ok))
    for key, expected in EXPECTED_RUN_CONTROLS.items():
        actual = config.get(key)
        try:
            ok = float(actual or 0) == float(expected)
        except (TypeError, ValueError):
            ok = False
        checks.append((key, actual, expected, ok))

    print("Frozen X25 + E2 + M3 check:")
    for label, actual, expected, ok in checks:
        print(f"  {'PASS' if ok else 'WARN'}  {label}: {actual!r}  (expected {expected!r})")


def derive_namespace(run: dict[str, Any], symbol: str) -> str:
    result = run.get("result") or {}
    provider_info = ((result.get("data") or {}).get("providers") or {}).get(symbol, {})
    provider = str(provider_info.get("provider") or "").strip()
    feed = str(provider_info.get("feed") or "").strip()
    adjustment = str(provider_info.get("adjustment") or "").strip()

    if provider == "alpaca" and feed and adjustment:
        return f"alpaca-{feed}-{adjustment}"

    # Current QQQ default in Ledger master.
    return "alpaca-sip-split"


def load_1m(
    store: MarketStore,
    namespace: str,
    symbol: str,
    run: dict[str, Any],
) -> pd.DataFrame:
    # Add several calendar days of warmup. Session-derived research fields themselves
    # reset daily, but this makes context robust around the requested boundary.
    start = pd.Timestamp(run.get("start_date")) - pd.Timedelta(days=10)
    end = pd.Timestamp(run.get("end_date")) + pd.Timedelta(days=2)
    start = start.tz_localize("America/New_York").tz_convert("UTC")
    end = end.tz_localize("America/New_York").tz_convert("UTC")

    frame = store.read_bars(namespace, symbol, "1m", start=start.isoformat(), end=end.isoformat())
    if frame.empty:
        raise RuntimeError(
            f"No cached 1m bars found for {symbol} in namespace {namespace!r}. "
            f"Expected under data/market/bars/{namespace}/1m/{symbol}.parquet"
        )

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
    frame["volume"] = frame["volume"].fillna(0.0)
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)

    # Canonical Ledger regular-session filtering. For 1m this keeps native bars.
    frame, _ = prepare_chart_bars(frame, "1m", "regular", session_profile="us_equity")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["available_at"] = completion_indexes({"1m": frame})["1m"]

    local = frame["timestamp"].dt.tz_convert(NY)
    frame["session_date"] = local.dt.strftime("%Y-%m-%d")
    frame["session_minute"] = local.dt.hour * 60 + local.dt.minute - RTH_OPEN_MINUTE

    # Canonical strategy v4 session VWAP: HLC3 weighted by volume, reset each RTH day.
    frame["hlc3"] = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    frame["pv"] = frame["hlc3"] * frame["volume"]
    group = frame.groupby("session_date", sort=False)
    frame["cum_volume"] = group["volume"].cumsum()
    frame["cum_pv"] = group["pv"].cumsum()
    frame["vwap"] = np.where(
        frame["cum_volume"] > 0,
        frame["cum_pv"] / frame["cum_volume"],
        np.nan,
    )
    return frame.reset_index(drop=True)


def get_signal_time(
    trade: dict[str, Any],
    all_1m: pd.DataFrame,
) -> tuple[pd.Timestamp | None, str]:
    """Return the entry decision time using Ledger's Trade Review fallback.

    Older saved runs predate recorded ``review_entry.signal_time`` metadata.
    ``trade_review.py`` reconstructs that time from the last primary bar whose
    *start* is before the recorded fill, then uses that bar's causal
    ``available_at`` timestamp.

    This is safer than simply treating the fill bar as completed: for a 1m fill
    at 09:33, the 09:33-09:34 candle is NOT available. The latest available
    decision bar is the 09:32 candle, available at 09:33.
    """
    metadata = trade.get("metadata") or {}
    recorded = (metadata.get("review_entry") or {}).get("signal_time")
    if recorded:
        try:
            return parse_utc(recorded), "recorded_review_entry"
        except Exception:
            pass

    fill_value = trade.get("entry_time")
    if not fill_value:
        return None, "missing"

    try:
        fill = parse_utc(fill_value)
    except Exception:
        return None, "missing"

    prior = all_1m.loc[all_1m["timestamp"] < fill]
    if prior.empty:
        return None, "missing"

    last = prior.iloc[-1]
    try:
        available_at = parse_utc(last["available_at"])
    except Exception:
        available_at = parse_utc(last["timestamp"]) + pd.Timedelta(minutes=1)

    # Match backend/app/services/trade_review.py's legacy inference path.
    return available_at, "reconstructed_trade_review_fallback"


def trailing(frame: pd.DataFrame, n: int) -> pd.DataFrame | None:
    return frame.tail(n) if len(frame) >= n else None


def efficiency_ratio(closes: pd.Series) -> float:
    x = pd.to_numeric(closes, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 2:
        return np.nan
    path = np.abs(np.diff(x)).sum()
    if path <= 0:
        return 0.0
    return float(abs(x[-1] - x[0]) / path)


def signed_efficiency_trade_relative(closes: pd.Series, direction: str) -> float:
    x = pd.to_numeric(closes, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 2:
        return np.nan
    path = np.abs(np.diff(x)).sum()
    if path <= 0:
        return 0.0
    signed = float((x[-1] - x[0]) / path)
    return signed if direction == "long" else -signed


def vwap_crossings(frame: pd.DataFrame) -> float:
    diff = (frame["close"] - frame["vwap"]).to_numpy(dtype=float)
    signs = np.sign(diff)
    # Exact VWAP touches are neutral. Remove them instead of inventing a side.
    signs = signs[np.isfinite(signs) & (signs != 0)]
    if len(signs) < 2:
        return 0.0
    return float(np.sum(signs[1:] != signs[:-1]))


def pct_closes_trade_side_vwap(frame: pd.DataFrame, direction: str) -> float:
    valid = frame.dropna(subset=["close", "vwap"])
    if valid.empty:
        return np.nan
    if direction == "long":
        return float((valid["close"] > valid["vwap"]).mean())
    return float((valid["close"] < valid["vwap"]).mean())


def consecutive_closes_trade_side_vwap(frame: pd.DataFrame, direction: str) -> int:
    count = 0
    for row in frame.dropna(subset=["close", "vwap"]).iloc[::-1].itertuples():
        supports = row.close > row.vwap if direction == "long" else row.close < row.vwap
        if not supports:
            break
        count += 1
    return count


def body_range_ratio(frame: pd.DataFrame) -> float:
    rng = (frame["high"] - frame["low"]).replace(0, np.nan)
    return float(((frame["close"] - frame["open"]).abs() / rng).mean())


def wick_fraction(frame: pd.DataFrame) -> float:
    rng = (frame["high"] - frame["low"]).replace(0, np.nan)
    upper = frame["high"] - frame[["open", "close"]].max(axis=1)
    lower = frame[["open", "close"]].min(axis=1) - frame["low"]
    return float(((upper + lower) / rng).mean())


def alternating_direction_count(frame: pd.DataFrame) -> float:
    signs = np.sign((frame["close"] - frame["open"]).to_numpy(dtype=float))
    signs = signs[signs != 0]
    if len(signs) < 2:
        return 0.0
    return float(np.sum(signs[1:] != signs[:-1]))


def candle_overlap_ratio(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return np.nan
    vals: list[float] = []
    rows = list(frame.itertuples())
    for prev, cur in zip(rows, rows[1:]):
        overlap = max(0.0, min(prev.high, cur.high) - max(prev.low, cur.low))
        smaller_range = min(prev.high - prev.low, cur.high - cur.low)
        if smaller_range > 0:
            vals.append(overlap / smaller_range)
    return float(np.mean(vals)) if vals else np.nan


def mean_true_range_bps(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return np.nan
    prev_close = frame["close"].shift(1)
    tr = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    base = finite(frame["close"].iloc[-1])
    if base is None or base <= 0:
        return np.nan
    return float(tr.dropna().mean() / base * 10_000.0)


def three_bar_swings(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    """
    Last confirmed 3-candle swing high/low.

    A centre bar becomes confirmed only after its right-hand neighbour has completed.
    Since `frame` contains only bars available by signal time, this is causal.
    """
    if len(frame) < 3:
        return None, None
    h = frame["high"].to_numpy(dtype=float)
    l = frame["low"].to_numpy(dtype=float)
    last_high = None
    last_low = None
    for i in range(1, len(frame) - 1):
        if h[i] > h[i - 1] and h[i] > h[i + 1]:
            last_high = float(h[i])
        if l[i] < l[i - 1] and l[i] < l[i + 1]:
            last_low = float(l[i])
    return last_high, last_low


def completed_htf(
    rth_1m: pd.DataFrame,
    signal_time: pd.Timestamp,
    timeframe: str,
) -> pd.DataFrame:
    # Use Ledger's own chart aggregation and completion-index semantics.
    base = rth_1m[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    bars, _ = prepare_chart_bars(base, timeframe, "regular", session_profile="us_equity")
    if bars.empty:
        return bars
    bars = bars.copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    available = completion_indexes({timeframe: bars})[timeframe]
    return bars.loc[available <= signal_time].reset_index(drop=True)


def htf_features(
    rth_1m: pd.DataFrame,
    signal_time: pd.Timestamp,
    direction: str,
    timeframe: str,
) -> dict[str, Any]:
    htf = completed_htf(rth_1m, signal_time, timeframe)
    prefix = f"research.completed_{timeframe}"
    out: dict[str, Any] = {
        f"{prefix}_bars_available": len(htf),
        f"{prefix}_last_bar_return_bps": np.nan,
        f"{prefix}_last_bar_trade_relative_return_bps": np.nan,
        f"{prefix}_3bar_efficiency": np.nan,
        f"{prefix}_3bar_trade_relative_efficiency": np.nan,
    }
    if htf.empty:
        return out

    last = htf.iloc[-1]
    last_ret = safe_bps(float(last["close"]), float(last["open"]))
    out[f"{prefix}_last_bar_return_bps"] = last_ret
    out[f"{prefix}_last_bar_trade_relative_return_bps"] = rel(last_ret, direction)

    if len(htf) >= 3:
        last3 = htf.tail(3)
        out[f"{prefix}_3bar_efficiency"] = efficiency_ratio(last3["close"])
        out[f"{prefix}_3bar_trade_relative_efficiency"] = signed_efficiency_trade_relative(
            last3["close"], direction
        )
    return out


def confirmation_features(
    trade: dict[str, Any],
    all_1m: pd.DataFrame,
    direction: str,
    signal_time: pd.Timestamp,
) -> dict[str, Any]:
    """Describe the entry-confirmation candles without using future bars.

    Prefer immutable recorded ``preceding_bars`` when available. Older saved runs
    do not have them, so fall back to the final three 1m bars completed by the
    reconstructed signal time. This mirrors the entry-confirmation reconstruction
    used by Trade Review for this frozen strategy family.
    """
    out: dict[str, Any] = {}
    metadata = trade.get("metadata") or {}
    review = metadata.get("review_entry") or {}
    stamps = review.get("preceding_bars") or []

    frame = pd.DataFrame()
    source = "unavailable"

    if stamps:
        parsed = []
        for stamp in stamps:
            try:
                parsed.append(parse_utc(stamp))
            except Exception:
                pass

        if parsed:
            indexed = all_1m.set_index("timestamp", drop=False)
            rows = []
            for stamp in parsed:
                if stamp in indexed.index:
                    row = indexed.loc[stamp]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[-1]
                    rows.append(row)
            if rows:
                frame = pd.DataFrame(rows).sort_values("timestamp")
                source = "recorded_review_entry.preceding_bars"

    if frame.empty:
        required = int(metadata.get("confirmation_bars") or 3)
        causal = all_1m.loc[all_1m["available_at"] <= signal_time].sort_values("timestamp")
        if len(causal) >= required:
            frame = causal.tail(required).copy()
            source = "reconstructed_completed_bars_at_signal"

    if frame.empty:
        out["research.confirmation_source"] = source
        return out

    out["research.confirmation_source"] = source
    out["research.confirmation_bars_available"] = len(frame)
    out["research.confirmation_net_displacement_bps"] = safe_bps(
        float(frame["close"].iloc[-1]), float(frame["open"].iloc[0])
    )
    out["research.confirmation_trade_relative_displacement_bps"] = rel(
        out["research.confirmation_net_displacement_bps"], direction
    )
    out["research.confirmation_avg_body_range_ratio"] = body_range_ratio(frame)
    out["research.confirmation_avg_wick_fraction"] = wick_fraction(frame)

    signed_distances = []
    matches = []
    for row in frame.itertuples():
        if not math.isfinite(float(row.vwap)) or row.vwap <= 0:
            signed_distances.append(np.nan)
            matches.append(False)
            continue
        distance = (float(row.close) - float(row.vwap)) / float(row.vwap) * 10_000.0
        trade_relative = distance if direction == "long" else -distance
        signed_distances.append(trade_relative)
        matches.append(trade_relative > 0)

    valid = [x for x in signed_distances if math.isfinite(x)]
    if valid:
        out["research.confirmation_first_trade_relative_vwap_distance_bps"] = valid[0]
        out["research.confirmation_final_trade_relative_vwap_distance_bps"] = valid[-1]
        out["research.confirmation_progress_bars"] = sum(
            1 for a, b in zip(valid, valid[1:]) if b > a
        )
        out["research.confirmation_all_on_trade_side"] = bool(all(matches))
        out["research.confirmation_reconstruction_status"] = (
            "PASS" if all(matches) else "MISMATCH"
        )
    return out

def features_for_trade(
    trade: dict[str, Any],
    all_1m: pd.DataFrame,
) -> dict[str, Any]:
    direction = str(trade.get("direction") or "").lower()
    out: dict[str, Any] = {
        "research.direction": direction,
        "research.feature_version": "vwap-entry-research-v1",
        "research.provenance": "reconstructed_current_market_cache",
    }
    if direction not in {"long", "short"}:
        out["research.warning"] = "unsupported_or_missing_direction"
        return out

    signal_time, signal_source = get_signal_time(trade, all_1m)
    out["research.signal_time_source"] = signal_source
    out["research.signal_time_utc"] = signal_time.isoformat() if signal_time is not None else ""

    if signal_time is None:
        out["research.warning"] = "missing_or_unreconstructable_entry_signal_time"
        return out

    local_signal = signal_time.tz_convert(NY)
    session_date = local_signal.strftime("%Y-%m-%d")

    # Exactly mirrors StrategyContext causality:
    # a 1m bar is available when timestamp + 1 minute <= decision/signal time.
    prior = all_1m[
        (all_1m["session_date"] == session_date)
        & (all_1m["available_at"] <= signal_time)
    ].copy()
    prior = prior.sort_values("timestamp").reset_index(drop=True)

    out["research.available_rth_1m_bars"] = len(prior)
    if prior.empty:
        out["research.warning"] = "no_completed_rth_bars_at_signal"
        return out

    current = prior.iloc[-1]
    current_price = float(current["close"])
    current_vwap = float(current["vwap"]) if math.isfinite(float(current["vwap"])) else np.nan
    out["research.signal_bar_start_utc"] = pd.Timestamp(current["timestamp"]).isoformat()
    out["research.signal_close"] = current_price
    out["research.signal_vwap"] = current_vwap
    out["research.minutes_since_open"] = float(current["session_minute"] + 1)

    for n in [5, 10, 20, 30]:
        w = trailing(prior, n)
        if w is None:
            out[f"research.vwap_crossings_{n}"] = np.nan
            out[f"research.efficiency_ratio_{n}"] = np.nan
            out[f"research.efficiency_trade_relative_{n}"] = np.nan
            continue
        out[f"research.vwap_crossings_{n}"] = vwap_crossings(w)
        out[f"research.efficiency_ratio_{n}"] = efficiency_ratio(w["close"])
        out[f"research.efficiency_trade_relative_{n}"] = signed_efficiency_trade_relative(
            w["close"], direction
        )

    for n in [5, 10, 20]:
        w = trailing(prior, n)
        if w is None:
            for suffix in [
                "pct_closes_trade_side_vwap",
                "vwap_slope_bps",
                "vwap_slope_trade_relative_bps",
                "mean_true_range_bps",
                "avg_body_range_ratio",
                "avg_wick_fraction",
            ]:
                out[f"research.{suffix}_{n}"] = np.nan
            continue

        out[f"research.pct_closes_trade_side_vwap_{n}"] = pct_closes_trade_side_vwap(w, direction)
        slope = safe_bps(float(w["vwap"].iloc[-1]), float(w["vwap"].iloc[0]))
        out[f"research.vwap_slope_bps_{n}"] = slope
        out[f"research.vwap_slope_trade_relative_bps_{n}"] = rel(slope, direction)
        out[f"research.mean_true_range_bps_{n}"] = mean_true_range_bps(w)
        out[f"research.avg_body_range_ratio_{n}"] = body_range_ratio(w)
        out[f"research.avg_wick_fraction_{n}"] = wick_fraction(w)

    for n in [10, 20]:
        w = trailing(prior, n)
        out[f"research.alternating_direction_count_{n}"] = (
            alternating_direction_count(w) if w is not None else np.nan
        )
        out[f"research.candle_overlap_ratio_{n}"] = (
            candle_overlap_ratio(w) if w is not None else np.nan
        )

    out["research.consecutive_closes_trade_side_vwap"] = consecutive_closes_trade_side_vwap(
        prior, direction
    )

    # Session/opening state known at the signal.
    session_open = float(prior["open"].iloc[0])
    session_high = float(prior["high"].max())
    session_low = float(prior["low"].min())
    session_range = session_high - session_low

    out["research.session_open"] = session_open
    out["research.session_high_so_far"] = session_high
    out["research.session_low_so_far"] = session_low
    out["research.open_to_signal_bps"] = safe_bps(current_price, session_open)
    out["research.open_to_signal_trade_relative_bps"] = rel(
        out["research.open_to_signal_bps"], direction
    )
    out["research.distance_below_session_high_bps"] = (
        (session_high - current_price) / session_high * 10_000.0
        if session_high > 0 else np.nan
    )
    out["research.distance_above_session_low_bps"] = (
        (current_price - session_low) / session_low * 10_000.0
        if session_low > 0 else np.nan
    )
    out["research.session_range_bps_so_far"] = (
        session_range / current_price * 10_000.0 if current_price > 0 else np.nan
    )

    if session_range > 0:
        position = (current_price - session_low) / session_range
        out["research.position_in_session_range"] = float(position)
        # 0 = still at the adverse extreme; 1 = fully rejected/recovered to other edge.
        out["research.retracement_from_adverse_session_extreme"] = (
            float(position) if direction == "long" else float(1.0 - position)
        )
    else:
        out["research.position_in_session_range"] = np.nan
        out["research.retracement_from_adverse_session_extreme"] = np.nan

    # Causal 3-candle swing context.
    swing_high, swing_low = three_bar_swings(prior)
    out["research.last_confirmed_swing_high"] = swing_high
    out["research.last_confirmed_swing_low"] = swing_low
    out["research.distance_to_swing_high_bps"] = (
        (swing_high - current_price) / current_price * 10_000.0
        if swing_high is not None and current_price > 0 else np.nan
    )
    out["research.distance_to_swing_low_bps"] = (
        (current_price - swing_low) / current_price * 10_000.0
        if swing_low is not None and current_price > 0 else np.nan
    )
    if direction == "long" and swing_high is not None:
        out["research.broke_recent_swing_trade_direction"] = bool(current_price > swing_high)
    elif direction == "short" and swing_low is not None:
        out["research.broke_recent_swing_trade_direction"] = bool(current_price < swing_low)
    else:
        out["research.broke_recent_swing_trade_direction"] = np.nan

    # Completed 5m/15m context using the same aggregation + completion contract as Ledger.
    session_frame = all_1m[all_1m["session_date"] == session_date].copy()
    out.update(htf_features(session_frame, signal_time, direction, "5m"))
    out.update(htf_features(session_frame, signal_time, direction, "15m"))

    # Exact recorded entry-confirmation bars when available.
    out.update(confirmation_features(trade, all_1m, direction, signal_time))

    out["research.warning"] = ""
    return out


def output_row(run_id: int, index: int, trade: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    metadata = trade.get("metadata") or {}
    row: dict[str, Any] = {
        "run_id": run_id,
        "trade_index_zero_based": index,
        "trade_number": index + 1,
        "symbol": trade.get("symbol"),
        "direction": trade.get("direction"),
        "entry_time": trade.get("entry_time"),
        "entry_price": trade.get("entry_price"),
        "exit_time": trade.get("exit_time"),
        "exit_price": trade.get("exit_price"),
        "exit_reason": trade.get("exit_reason"),
        "net_pnl": trade.get("net_pnl"),
        "pnl_pct": trade.get("pnl_pct"),
        "r_multiple": trade.get("r_multiple"),
        "signal_reason": trade.get("signal_reason"),
        "recorded_htf_trend_state": metadata.get("htf_trend_state"),
        "recorded_htf_filter_passed": metadata.get("htf_filter_passed"),
        "recorded_htf_close": metadata.get("htf_close"),
        "recorded_htf_ema": metadata.get("htf_ema"),
        "recorded_entry_vwap": metadata.get("vwap"),
        "recorded_confirmation_count": metadata.get("confirmation_count"),
    }
    if trade.get("entry_time") and trade.get("exit_time"):
        try:
            row["duration_minutes"] = (
                parse_utc(trade["exit_time"]) - parse_utc(trade["entry_time"])
            ).total_seconds() / 60.0
        except Exception:
            row["duration_minutes"] = np.nan
    else:
        row["duration_minutes"] = np.nan

    row.update(features)
    return row


def process_run(
    repo: BacktestRunRepository,
    store: MarketStore,
    run_id: int,
    out_dir: Path,
) -> Path:
    run = run_snapshot(repo, run_id)
    print_run_check(run)

    result = run.get("result") or {}
    trades = result.get("trades") or []
    symbols = result.get("symbols") or run.get("symbols") or []
    primary = result.get("primary_timeframe")

    if primary != "1m":
        raise RuntimeError(f"Run {run_id} is {primary!r}, expected 1m.")
    if len(symbols) != 1 or str(symbols[0]).upper() != "QQQ":
        raise RuntimeError(f"Run {run_id} symbols are {symbols!r}; this research tool expects QQQ only.")
    if not trades:
        raise RuntimeError(f"Run {run_id} has no saved trades.")

    symbol = "QQQ"
    namespace = derive_namespace(run, symbol)
    bars = load_1m(store, namespace, symbol, run)

    print(
        f"Using cache namespace {namespace}; "
        f"{len(bars):,} RTH 1m bars from "
        f"{bars['timestamp'].min()} to {bars['timestamp'].max()}."
    )
    print(f"Saved trades: {len(trades):,}")

    rows = []
    missing_signal = 0
    reconstructed_signal = 0
    for index, trade in enumerate(trades):
        features = features_for_trade(trade, bars)
        if features.get("research.warning") == "missing_or_unreconstructable_entry_signal_time":
            missing_signal += 1
        if features.get("research.signal_time_source") == "reconstructed_trade_review_fallback":
            reconstructed_signal += 1
        rows.append(output_row(run_id, index, trade, features))

    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"run-{run_id}-entry-features.csv"
    df.to_csv(path, index=False, encoding="utf-8")

    print(f"Wrote: {path}")
    print(f"Rows: {len(df):,}; columns: {len(df.columns):,}")
    if reconstructed_signal:
        print(
            f"Info: reconstructed signal time for {reconstructed_signal} older trades "
            "using the same last-completed-primary-bar fallback as Trade Review."
        )
    if missing_signal:
        print(
            f"WARNING: {missing_signal} trades still lacked enough information to reconstruct "
            "an entry signal time; their signal-time research fields remain unavailable."
        )
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate causal research-only entry features for existing Ledger VWAP runs."
    )
    parser.add_argument(
        "--run-id",
        type=int,
        nargs="+",
        required=True,
        help="One or more immutable Ledger saved-run IDs, e.g. --run-id 173 175",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("research_output"),
        help="Output directory relative to the backend working directory.",
    )
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_path)
    repo = BacktestRunRepository(database)
    store = MarketStore(settings.market_data_dir)

    print(f"Ledger DB: {settings.database_path.resolve()}")
    print(f"Market cache: {settings.market_data_dir.resolve()}")

    paths = []
    for run_id in args.run_id:
        paths.append(process_run(repo, store, run_id, args.out_dir))

    print()
    print("Done. Upload these CSVs back to ChatGPT:")
    for path in paths:
        print(f"  {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
