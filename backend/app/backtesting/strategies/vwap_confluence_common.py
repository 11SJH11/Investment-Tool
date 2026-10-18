"""Shared causal helpers for isolated VWAP D6 confluence research children.

Research-only.  These helpers never alter exits, fills, sizing, costs, session
controls or the frozen VWAP/D6/X25/E2/EMA20 logic.  Child strategies use the
entry/reversal-only hook already present in VWAP research v5.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from app.backtesting.strategies.vwap_trend_confirmation_quality_research_v5 import (
    VwapTrendConfirmationQualityResearchV5,
)

NY = ZoneInfo("America/New_York")
RTH_OPEN = 9 * 60 + 30
RTH_CLOSE = 16 * 60


@dataclass(frozen=True)
class Pivot:
    side: str
    price: float
    occurred_at: pd.Timestamp
    confirmed_at: pd.Timestamp
    session_date: object


@dataclass(frozen=True)
class BreakEvent:
    side: str
    time: pd.Timestamp
    pivot_price: float
    session_date: object


def _utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _rth(frame: pd.DataFrame, timeframe: str = "1m") -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    local = out["timestamp"].dt.tz_convert(NY)
    minute = local.dt.hour * 60 + local.dt.minute
    mask = (minute >= RTH_OPEN) & (minute < RTH_CLOSE)
    out = out.loc[mask].copy()
    if out.empty:
        return out
    local = out["timestamp"].dt.tz_convert(NY)
    out["session_date"] = local.dt.date.values
    out["session_minute"] = (local.dt.hour * 60 + local.dt.minute - RTH_OPEN).astype(int).values
    if "available_at" in out:
        out["available_at"] = pd.to_datetime(out["available_at"], utc=True)
    else:
        minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60}.get(str(timeframe))
        if minutes is None:
            raise ValueError(f"Unsupported confluence timeframe: {timeframe}")
        out["available_at"] = out["timestamp"] + pd.Timedelta(minutes=minutes)
    out = out.sort_values("timestamp").reset_index(drop=True)
    previous_close = out["close"].astype(float).shift(1)
    tr = pd.concat([
        out["high"].astype(float) - out["low"].astype(float),
        (out["high"].astype(float) - previous_close).abs(),
        (out["low"].astype(float) - previous_close).abs(),
    ], axis=1).max(axis=1)
    out["tr_bps"] = np.where(out["close"].astype(float) > 0, tr / out["close"].astype(float) * 10000.0, np.nan)
    return out


def current_and_prior_dates(frame: pd.DataFrame, prior: int) -> list:
    if frame.empty:
        return []
    dates = list(dict.fromkeys(frame["session_date"].tolist()))
    return dates[-(prior + 1):]


def strict_pivots(frame: pd.DataFrame, strength: int) -> list[Pivot]:
    """Strict unique N/N pivots; no pivot window crosses an RTH boundary."""
    if frame.empty or len(frame) < strength * 2 + 1:
        return []
    output: list[Pivot] = []
    for date, session in frame.groupby("session_date", sort=True):
        session = session.reset_index(drop=True)
        if len(session) < strength * 2 + 1:
            continue
        highs = session["high"].to_numpy(dtype=float)
        lows = session["low"].to_numpy(dtype=float)
        for i in range(strength, len(session) - strength):
            left, right = i - strength, i + strength + 1
            hw = highs[left:right]
            lw = lows[left:right]
            if highs[i] == np.max(hw) and int(np.sum(hw == highs[i])) == 1:
                output.append(Pivot(
                    "high", float(highs[i]), _utc(session.iloc[i]["timestamp"]),
                    _utc(session.iloc[i + strength]["available_at"]), date,
                ))
            if lows[i] == np.min(lw) and int(np.sum(lw == lows[i])) == 1:
                output.append(Pivot(
                    "low", float(lows[i]), _utc(session.iloc[i]["timestamp"]),
                    _utc(session.iloc[i + strength]["available_at"]), date,
                ))
    output.sort(key=lambda p: (p.confirmed_at, p.occurred_at))
    return output


def break_events(frame: pd.DataFrame, pivots: list[Pivot]) -> list[BreakEvent]:
    """First completed close through the latest already-confirmed pivot.

    Mirrors the diagnostic BOS interpretation: one event per latest pivot and the
    pivot must already be confirmed before the breaking bar completes.
    """
    if frame.empty or not pivots:
        return []
    latest = {"high": None, "low": None}
    consumed: set[tuple[str, int]] = set()
    events: list[BreakEvent] = []
    ordered = sorted(pivots, key=lambda p: (p.confirmed_at, p.occurred_at))
    pi = 0
    for row in frame.itertuples(index=False):
        available = _utc(row.available_at)
        while pi < len(ordered) and ordered[pi].confirmed_at <= available:
            latest[ordered[pi].side] = ordered[pi]
            pi += 1
        for pivot_side, event_side in (("high", "bullish"), ("low", "bearish")):
            pivot = latest[pivot_side]
            if pivot is None or pivot.confirmed_at >= available:
                continue
            identity = (pivot_side, int(pivot.occurred_at.value))
            if identity in consumed:
                continue
            crossed = float(row.close) > pivot.price if pivot_side == "high" else float(row.close) < pivot.price
            if crossed:
                events.append(BreakEvent(event_side, available, pivot.price, row.session_date))
                consumed.add(identity)
    return events


def structure_state(pivots: list[Pivot], dates: set) -> str:
    highs = [p for p in pivots if p.side == "high" and p.session_date in dates]
    lows = [p for p in pivots if p.side == "low" and p.session_date in dates]
    high_state = "unknown"
    low_state = "unknown"
    if len(highs) >= 2:
        high_state = "HH" if highs[-1].price > highs[-2].price else "LH" if highs[-1].price < highs[-2].price else "EH"
    if len(lows) >= 2:
        low_state = "HL" if lows[-1].price > lows[-2].price else "LL" if lows[-1].price < lows[-2].price else "EL"
    if high_state == "HH" and low_state == "HL":
        return "bullish"
    if high_state == "LH" and low_state == "LL":
        return "bearish"
    if high_state != "unknown" or low_state != "unknown":
        return "mixed"
    return "unknown"


def mss15_rolling_s2(ctx, side: str) -> tuple[bool, dict]:
    bars = _rth(ctx.bars("15m", count=240), "15m")
    dates = current_and_prior_dates(bars, 5)
    if not dates:
        return False, {"status": "missing_15m_history"}
    # Keep one extra session in the event construction so a pivot just outside the
    # rolling structure window may still be broken inside the declared window.
    all_dates = current_and_prior_dates(bars, 7)
    use = bars.loc[bars["session_date"].isin(all_dates)].reset_index(drop=True)
    pivots = strict_pivots(use, 2)
    events = break_events(use, pivots)
    wanted = "bullish" if side == "long" else "bearish"
    opposite = "bearish" if wanted == "bullish" else "bullish"
    rolling = set(dates)
    state = structure_state(pivots, rolling)
    matching = [e for e in events if e.side == wanted and e.session_date in rolling]
    latest = matching[-1] if matching else None
    passed = latest is not None and state in {opposite, "mixed"}
    return passed, {
        "timeframe": "15m", "swing_strength": 2, "rolling_sessions": len(dates),
        "structure_state": state, "directional_bos_exists": latest is not None,
        "directional_bos_time": latest.time.isoformat() if latest else "",
    }


def bos1m_s2_within_15m(ctx, side: str) -> tuple[bool, dict]:
    bars = _rth(ctx.bars("1m", count=900))
    if bars.empty:
        return False, {"status": "missing_1m_history"}
    dates = current_and_prior_dates(bars, 1)
    use = bars.loc[bars["session_date"].isin(dates)].reset_index(drop=True)
    pivots = strict_pivots(use, 2)
    events = break_events(use, pivots)
    current_date = use.iloc[-1]["session_date"]
    wanted = "bullish" if side == "long" else "bearish"
    matching = [e for e in events if e.side == wanted and e.session_date == current_date]
    latest = matching[-1] if matching else None
    now = _utc(ctx.decision_time)
    minutes = (now - latest.time).total_seconds() / 60.0 if latest else math.nan
    passed = latest is not None and 0.0 <= minutes <= 15.0
    return passed, {
        "timeframe": "1m", "swing_strength": 2,
        "directional_bos_time": latest.time.isoformat() if latest else "",
        "directional_bos_minutes_ago": minutes,
    }


def _fvg_events(frame: pd.DataFrame) -> list[dict]:
    events: list[dict] = []
    if frame.empty:
        return events
    for date, session in frame.groupby("session_date", sort=True):
        session = session.reset_index(drop=True)
        if len(session) < 3:
            continue
        for i in range(2, len(session)):
            a = session.iloc[i - 2]
            c = session.iloc[i]
            if float(c.low) > float(a.high):
                lower, upper, fside = float(a.high), float(c.low), "bullish"
            elif float(c.high) < float(a.low):
                lower, upper, fside = float(c.high), float(a.low), "bearish"
            else:
                continue
            base = float(a.close)
            size_bps = (upper - lower) / base * 10000.0 if base > 0 else math.nan
            full_time = None
            # Same-session fill semantics intentionally match the discovery tool.
            for j in range(i + 1, len(session)):
                future = session.iloc[j]
                full = float(future.low) <= lower if fside == "bullish" else float(future.high) >= upper
                if full:
                    full_time = _utc(future.available_at)
                    break
            events.append({
                "side": fside, "created": _utc(c.available_at), "date": date,
                "size_bps": float(size_bps), "full_time": full_time,
            })
    events.sort(key=lambda e: e["created"])
    return events


def no_unfilled_opposing_fvg15(ctx, side: str) -> tuple[bool, dict]:
    bars = _rth(ctx.bars("15m", count=240), "15m")
    dates = current_and_prior_dates(bars, 5)
    if not dates:
        return False, {"status": "missing_15m_history"}
    use = bars.loc[bars["session_date"].isin(dates)].reset_index(drop=True)
    events = _fvg_events(use)
    opposing = "bearish" if side == "long" else "bullish"
    candidates = [e for e in events if e["side"] == opposing and e["date"] in set(dates)]
    latest = candidates[-1] if candidates else None
    now = _utc(ctx.decision_time)
    unresolved = bool(latest and (latest["full_time"] is None or latest["full_time"] > now))
    return not unresolved, {
        "timeframe": "15m", "rolling_sessions": len(dates),
        "opposing_fvg_exists": latest is not None,
        "opposing_fvg_created": latest["created"].isoformat() if latest else "",
        "opposing_fvg_size_bps": latest["size_bps"] if latest else None,
        "opposing_fvg_unfilled": unresolved,
    }


def directional_fvg1m_5bps_30m(ctx, side: str) -> tuple[bool, dict]:
    bars = _rth(ctx.bars("1m", count=500))
    if bars.empty:
        return False, {"status": "missing_1m_history"}
    current_date = bars.iloc[-1]["session_date"]
    current = bars.loc[bars["session_date"] == current_date].reset_index(drop=True)
    wanted = "bullish" if side == "long" else "bearish"
    events = _fvg_events(current)
    now = _utc(ctx.decision_time)
    candidates = [
        e for e in events if e["side"] == wanted and e["size_bps"] >= 5.0
        and 0.0 <= (now - e["created"]).total_seconds() / 60.0 <= 30.0
    ]
    latest = candidates[-1] if candidates else None
    return latest is not None, {
        "timeframe": "1m", "minimum_fvg_bps": 5.0, "lookback_minutes": 30,
        "directional_fvg_created": latest["created"].isoformat() if latest else "",
        "directional_fvg_size_bps": latest["size_bps"] if latest else None,
    }


def extreme_chop_score(ctx) -> tuple[int | None, dict]:
    bars = _rth(ctx.bars("1m", count=500))
    if bars.empty:
        return None, {"status": "missing_1m_history"}
    date = bars.iloc[-1]["session_date"]
    prior = bars.loc[bars["session_date"] == date].reset_index(drop=True)
    if len(prior) < 40:
        return None, {"status": "insufficient_current_session_bars", "bars": len(prior)}

    # Running session VWAP, matching the discovery calculation.
    vol = pd.to_numeric(prior["volume"], errors="coerce").fillna(0.0)
    hlc3 = (prior["high"].astype(float) + prior["low"].astype(float) + prior["close"].astype(float)) / 3.0
    cum_vol = vol.cumsum()
    prior["_vwap"] = np.where(cum_vol > 0, (hlc3 * vol).cumsum() / cum_vol, np.nan)

    last20 = prior.tail(20)
    closes = last20["close"].astype(float).to_numpy()
    path = float(np.abs(np.diff(closes)).sum()) if len(closes) >= 2 else 0.0
    efficiency = abs(float(closes[-1] - closes[0])) / path if path > 0 else 0.0

    overlaps = []
    rows = list(last20.itertuples(index=False))
    for prev, cur in zip(rows, rows[1:]):
        overlap = max(0.0, min(float(prev.high), float(cur.high)) - max(float(prev.low), float(cur.low)))
        smaller = min(float(prev.high) - float(prev.low), float(cur.high) - float(cur.low))
        if smaller > 0:
            overlaps.append(overlap / smaller)
    overlap_ratio = float(np.mean(overlaps)) if overlaps else math.nan

    diff = (last20["close"].astype(float) - last20["_vwap"].astype(float)).to_numpy()
    signs = np.sign(diff)
    signs = signs[np.isfinite(signs) & (signs != 0)]
    crossings = int(np.sum(signs[1:] != signs[:-1])) if len(signs) >= 2 else 0

    tr_bps = prior["tr_bps"].astype(float).to_numpy()
    recent10 = np.asarray(tr_bps[-10:], dtype=float)
    previous30 = np.asarray(tr_bps[-40:-10], dtype=float)
    contraction = float(np.nanmean(recent10) / np.nanmean(previous30)) if np.nanmean(previous30) > 0 else math.nan

    flags = [
        efficiency <= 0.35,
        math.isfinite(overlap_ratio) and overlap_ratio >= 0.55,
        crossings >= 2,
        math.isfinite(contraction) and contraction <= 0.85,
    ]
    score = int(sum(flags))
    return score, {
        "accumulation_proxy_score": score,
        "efficiency_20m": efficiency,
        "overlap_20m": overlap_ratio,
        "vwap_crosses_20m": crossings,
        "tr_ratio_10_vs_prev30": contraction,
    }


def previous_session_levels(ctx, count: int) -> tuple[list[pd.DataFrame], pd.DataFrame]:
    bars = _rth(ctx.bars("1m", count=max(2200, (count + 2) * 390)))
    if bars.empty:
        return [], bars
    current_date = bars.iloc[-1]["session_date"]
    current = bars.loc[bars["session_date"] == current_date].reset_index(drop=True)
    dates = [d for d in list(dict.fromkeys(bars["session_date"].tolist())) if d < current_date]
    use_dates = dates[-count:]
    previous = [bars.loc[bars["session_date"] == d].reset_index(drop=True) for d in use_dates]
    return previous, current


def short_sellside_untaken(ctx, side: str, sessions: int) -> tuple[bool, dict]:
    if side != "short":
        return True, {"applies_to": "short_only", "long_passthrough": True}
    previous, current = previous_session_levels(ctx, sessions)
    if not previous or current.empty:
        return True, {"applies_to": "short_only", "status": "insufficient_prior_session_history"}
    if sessions == 1:
        level = float(previous[-1]["low"].min())
        label = "pdl"
    else:
        level = min(float(frame["low"].min()) for frame in previous)
        label = f"prior_{sessions}d_low"
    taken = bool((current["low"].astype(float) < level).any())
    return not taken, {
        "applies_to": "short_only", "level_name": label, "level": level,
        "sellside_taken_before_signal": taken,
    }


def causal_swing_s5_samebar_within5(ctx, side: str) -> tuple[bool, dict]:
    """Causality-corrected strict-5 adverse swing sweep/reclaim.

    Unlike the first discovery script, a pivot must be confirmed BEFORE the bar
    that sweeps it.  This is therefore a new development hypothesis; do not spend
    untouched holdout data on it until it is re-diagnosed on development data.
    """
    bars = _rth(ctx.bars("1m", count=2800))
    if bars.empty:
        return False, {"status": "missing_1m_history"}
    current_date = bars.iloc[-1]["session_date"]
    dates = current_and_prior_dates(bars, 5)
    use = bars.loc[bars["session_date"].isin(dates)].reset_index(drop=True)
    pivots = strict_pivots(use, 5)
    adverse = "low" if side == "long" else "high"
    candidates = [p for p in pivots if p.side == adverse and p.confirmed_at <= _utc(ctx.decision_time)][-6:]
    current = use.loc[use["session_date"] == current_date].reset_index(drop=True)
    now = _utc(ctx.decision_time)
    latest = None
    for pivot in candidates:
        eligible = current.loc[pd.to_datetime(current["available_at"], utc=True) >= pivot.confirmed_at]
        for row in eligible.itertuples(index=False):
            if adverse == "low":
                swept = float(row.low) < pivot.price and float(row.close) > pivot.price
            else:
                swept = float(row.high) > pivot.price and float(row.close) < pivot.price
            if swept:
                event_time = _utc(row.available_at)
                if latest is None or event_time > latest:
                    latest = event_time
    minutes = (now - latest).total_seconds() / 60.0 if latest is not None else math.nan
    return latest is not None and 0.0 <= minutes <= 5.0, {
        "swing_strength": 5, "same_bar_reclaim": True,
        "causality_corrected_vs_discovery_v2": True,
        "sweep_minutes_ago": minutes,
    }


def make_spec(key: str, name: str, description: str, source_file: str, confluence_text: str):
    parent = VwapTrendConfirmationQualityResearchV5.spec
    defaults = dict(parent.defaults)
    defaults["min_confirmation_displacement_bps"] = 6.0
    parameters = tuple(
        replace(p, default=6.0) if p.key == "min_confirmation_displacement_bps" else p
        for p in parent.parameters
    )
    risk = dict(parent.risk_management)
    risk["Research confluence"] = confluence_text
    return replace(
        parent,
        key=key,
        name=name,
        description=description,
        defaults=defaults,
        parameters=parameters,
        category="Published research · confluence isolation",
        risk_management=risk,
        source_file=source_file,
    )


class FrozenD6ConfluenceBase(VwapTrendConfirmationQualityResearchV5):
    """Frozen D6 baseline plus exactly one entry/reversal-only confluence."""

    CONFLUENCE_ID = "override_me"

    def __init__(self, **params):
        params.setdefault("min_confirmation_displacement_bps", 6.0)
        super().__init__(**params)
        self._last_confluence_meta: dict = {}

    def reset(self):
        super().reset()
        self._last_confluence_meta = {}

    def _confluence_allows(self, ctx, side: str) -> tuple[bool, dict]:
        raise NotImplementedError

    def _distance_allows(self, close, vwap_value):
        if not super()._distance_allows(close, vwap_value):
            return False
        ctx = self._v5_ctx
        side = self._streak_side
        if ctx is None or side not in {"long", "short"}:
            self._last_confluence_meta = {
                "confluence_id": self.CONFLUENCE_ID,
                "confluence_passed": False,
                "status": "missing_context_or_side",
            }
            return False
        allowed, detail = self._confluence_allows(ctx, side)
        self._last_confluence_meta = {
            "confluence_id": self.CONFLUENCE_ID,
            "confluence_passed": bool(allowed),
            **dict(detail or {}),
        }
        return bool(allowed)

    def _entry(self, ctx, side, vwap_value, trend_meta):
        from dataclasses import replace as dc_replace

        meta = dict(trend_meta or {})
        pending_confluence = meta.pop("_confluence_meta", None)
        detail = dict(pending_confluence or self._last_confluence_meta or {})
        signal = super()._entry(ctx, side, vwap_value, meta)
        metadata = {
            **dict(signal.metadata),
            "research_confluence_id": self.CONFLUENCE_ID,
            "research_confluence_passed": True,
            "research_confluence_detail": detail,
        }
        return dc_replace(signal, metadata=metadata)

    def on_bar(self, ctx):
        self._last_confluence_meta = {}
        decision = super().on_bar(ctx)
        if self._pending_reverse is not None and self._pending_meta is not None and self._last_confluence_meta:
            self._pending_meta = {
                **dict(self._pending_meta),
                "_confluence_meta": dict(self._last_confluence_meta),
            }
        return decision
