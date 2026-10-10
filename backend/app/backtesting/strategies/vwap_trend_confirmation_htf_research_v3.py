"""VWAP Trend Confirmation + self-contained HTF filter — Ledger research v3.

This version is designed for Ledger's current UI, where a 1m run does not expose
an "additional timeframes" selector.

It uses ONLY completed 1-minute bars from StrategyContext and causally constructs
higher-timeframe closes internally for the optional trend filter.

Core signal
-----------
- 1m session VWAP, HLC3 weighted by volume, reset at 09:30 ET.
- Require N consecutive completed closes on one side of VWAP (default 2).
- Optional HTF regime filter:
    LONG only when last completed HTF close > EMA(HTF closes)
    SHORT only when last completed HTF close < EMA(HTF closes)
- HTF options: off, 1h, 4h, 1d, 1w.
- HTF filter applies to new entries/reversals only.
- Opposite confirmed VWAP signal still exits the current position even when HTF
  blocks the reverse entry.

Causality / HTF construction
----------------------------
Only completed 1m bars are used.
- 1h: completed 60-minute RTH blocks anchored at 09:30 ET.
- 4h: completed 09:30-13:30 RTH blocks. The shorter 13:30-16:00 remainder is not
  treated as a 4h bar.
- 1d: completed 09:30-16:00 RTH sessions only.
- 1w: completed calendar weeks built from completed daily RTH closes; current
  partial week is excluded.

The 4h definition is therefore explicitly an RTH 4-hour block, not an extended-
hours provider candle.

Ledger still cannot atomically reverse at the same next-bar open. This preserves
the existing v2 delayed-reversal behaviour.

The source VWAP trend idea has no protective stop. Ledger requires one, so a very
wide engine-only safety stop is used. Use position-value sizing, not risk sizing.
"""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo
import math
import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "vwap_trend_confirmation_htf_research_v3"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "confirmation_bars": 2,
    "min_minutes_after_open": 1,
    "trend_timeframe": "off",       # off | 1h | 4h | 1d | 1w
    "trend_ema_length": 20,
    "engine_safety_stop_pct": 90.0,
}


def _normalise_1m(frame):
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return pd.DataFrame()

    out = frame.copy()
    ts = pd.to_datetime(out["timestamp"], utc=True).dt.tz_convert(NY)
    mins_clock = ts.dt.hour * 60 + ts.dt.minute
    mask = (mins_clock >= 570) & (mins_clock < 960)

    out = out.loc[mask].copy()
    ts = ts.loc[mask]
    if out.empty:
        return out

    out["_ts_et"] = ts.values
    out["_date"] = ts.dt.date.values
    out["_session_minute"] = (mins_clock.loc[mask] - 570).astype(int).values
    return out.reset_index(drop=True)


def _today_rth(frame):
    out = _normalise_1m(frame)
    if out.empty:
        return out
    day = out.iloc[-1]["_date"]
    return out.loc[out["_date"] == day].reset_index(drop=True)


def _vwap(frame):
    volume = frame["volume"].astype(float)
    total = float(volume.sum())
    if total <= 0:
        return None

    tp = (
        frame["high"].astype(float)
        + frame["low"].astype(float)
        + frame["close"].astype(float)
    ) / 3.0
    return float((tp * volume).sum() / total)


def _safety_stop(reference, direction, pct):
    f = float(pct) / 100.0
    if direction == "long":
        return max(1e-9, float(reference) * (1.0 - f))
    return float(reference) * (1.0 + f)


def _history_count(timeframe, ema_length):
    n = int(ema_length)
    if timeframe == "1h":
        return max(2500, n * 90)
    if timeframe in {"4h", "1d"}:
        return max(12000, n * 520)
    if timeframe == "1w":
        return max(50000, n * 2300)
    return 500


def _completed_1h_closes(frame):
    f = _normalise_1m(frame)
    if f.empty:
        return pd.Series(dtype=float)

    f["_bucket"] = (f["_session_minute"] // 60).astype(int)
    rows = []
    for (day, bucket), g in f.groupby(["_date", "_bucket"], sort=True):
        # Six full 60-minute RTH blocks exist from 09:30 through 15:30.
        # The final 30-minute remainder is not called a 1h bar.
        if int(bucket) > 5 or len(g) != 60:
            continue
        if g["_session_minute"].iloc[0] != int(bucket) * 60:
            continue
        if g["_session_minute"].iloc[-1] != int(bucket) * 60 + 59:
            continue
        rows.append(float(g.iloc[-1]["close"]))
    return pd.Series(rows, dtype=float)


def _completed_4h_closes(frame):
    f = _normalise_1m(frame)
    if f.empty:
        return pd.Series(dtype=float)

    rows = []
    for day, g in f.groupby("_date", sort=True):
        block = g.loc[(g["_session_minute"] >= 0) & (g["_session_minute"] < 240)]
        if len(block) != 240:
            continue
        if int(block["_session_minute"].iloc[0]) != 0:
            continue
        if int(block["_session_minute"].iloc[-1]) != 239:
            continue
        rows.append(float(block.iloc[-1]["close"]))
    return pd.Series(rows, dtype=float)


def _completed_daily_closes(frame):
    f = _normalise_1m(frame)
    if f.empty:
        return pd.DataFrame(columns=["date", "close"])

    rows = []
    for day, g in f.groupby("_date", sort=True):
        # A complete US cash session contains 390 one-minute bars.
        if len(g) != 390:
            continue
        if int(g["_session_minute"].iloc[0]) != 0:
            continue
        if int(g["_session_minute"].iloc[-1]) != 389:
            continue
        rows.append({"date": day, "close": float(g.iloc[-1]["close"])})
    return pd.DataFrame(rows)


def _completed_weekly_closes(frame, decision_time):
    daily = _completed_daily_closes(frame)
    if daily.empty:
        return pd.Series(dtype=float)

    now_date = decision_time.astimezone(NY).date()
    current_week = now_date - timedelta(days=now_date.weekday())

    daily["week"] = [
        d - timedelta(days=d.weekday())
        for d in daily["date"]
    ]
    daily = daily.loc[daily["week"] < current_week].copy()
    if daily.empty:
        return pd.Series(dtype=float)

    weekly = (
        daily.sort_values("date")
        .groupby("week", sort=True)
        .tail(1)
        .sort_values("week")
    )
    return weekly["close"].astype(float).reset_index(drop=True)


def _trend_cache_key(decision_time, timeframe):
    et = decision_time.astimezone(NY)
    d = et.date()
    minute = et.hour * 60 + et.minute - 570

    if timeframe == "1h":
        return (d, max(-1, minute // 60))
    if timeframe == "4h":
        return (d, 1 if minute >= 240 else 0)
    if timeframe == "1d":
        return d
    if timeframe == "1w":
        return d - timedelta(days=d.weekday())
    return "off"


def _ema_state(closes, length):
    if closes is None or len(closes) < int(length):
        return None, None, None

    closes = pd.Series(closes, dtype=float).dropna().reset_index(drop=True)
    if len(closes) < int(length):
        return None, None, None

    ema = closes.ewm(span=int(length), adjust=False).mean()
    close = float(closes.iloc[-1])
    ema_value = float(ema.iloc[-1])

    if not (math.isfinite(close) and math.isfinite(ema_value)):
        return None, None, None
    if close > ema_value:
        return "long", close, ema_value
    if close < ema_value:
        return "short", close, ema_value
    return None, close, ema_value


@strategy_registry.register
class VwapTrendConfirmationHtfResearchV3(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="VWAP Trend Confirmation + HTF · research v3",
        description=(
            "VWAP confirmation v2 plus optional self-contained HTF EMA trend "
            "alignment built causally from the run's completed 1m bars."
        ),
        defaults=DEFAULTS,
        timeframes=("1m",),
        category="Published research · refinement",
        parameters=(
            ParameterSpec(
                "direction", "Direction", "choice", "both",
                choices=("both", "long", "short"),
            ),
            ParameterSpec(
                "confirmation_bars", "Consecutive closes for confirmation", "int",
                2, 1, 10, 1,
            ),
            ParameterSpec(
                "min_minutes_after_open", "Earliest signal · minutes after 09:30", "int",
                1, 1, 120, 1,
            ),
            ParameterSpec(
                "trend_timeframe", "Higher-timeframe trend filter", "choice", "off",
                choices=("off", "1h", "4h", "1d", "1w"),
                help="Long only above completed HTF EMA; short only below.",
            ),
            ParameterSpec(
                "trend_ema_length", "Higher-timeframe EMA length", "int",
                20, 5, 200, 5,
            ),
            ParameterSpec(
                "engine_safety_stop_pct", "Engine-only catastrophic stop · %", "float",
                90.0, 20.0, 99.0, 1.0,
            ),
        ),
        risk_management={
            "Signal": "N consecutive completed 1m closes on one side of session VWAP.",
            "HTF confluence": "New entries align with completed HTF close vs HTF EMA.",
            "Exit": "Opposite VWAP confirmation exits even if HTF blocks reverse entry.",
            "Session": "Force flat at 16:00 with allow_overnight=False.",
            "Stop": "Wide engine-only safety stop; use position-value sizing.",
        },
        source_file="backend/app/backtesting/strategies/vwap_trend_confirmation_htf_research_v3.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown VWAP confirmation HTF parameter")
        super().__init__(**params)

        if str(self.params["direction"]) not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")
        if str(self.params["trend_timeframe"]) not in {"off", "1h", "4h", "1d", "1w"}:
            raise ValueError("trend_timeframe must be off, 1h, 4h, 1d or 1w")

        self.params["confirmation_bars"] = int(self.params["confirmation_bars"])
        self.params["min_minutes_after_open"] = int(self.params["min_minutes_after_open"])
        self.params["trend_ema_length"] = int(self.params["trend_ema_length"])
        self.params["engine_safety_stop_pct"] = float(self.params["engine_safety_stop_pct"])

        self.reset()

    def reset(self):
        self._session_date = None
        self._streak_side = None
        self._streak_count = 0
        self._pending_reverse = None
        self._pending_meta = None
        self._trend_cache_key_value = None
        self._trend_cache_value = (None, None, None)

    def _update_streak(self, side):
        if side is None:
            self._streak_side = None
            self._streak_count = 0
            return
        if side == self._streak_side:
            self._streak_count += 1
        else:
            self._streak_side = side
            self._streak_count = 1

    def _trend_state(self, ctx):
        tf = str(self.params["trend_timeframe"])
        if tf == "off":
            return "both", None, None

        key = (tf, _trend_cache_key(ctx.decision_time, tf))
        if key == self._trend_cache_key_value:
            return self._trend_cache_value

        count = _history_count(tf, int(self.params["trend_ema_length"]))
        history = ctx.bars("1m", count=count)

        if tf == "1h":
            closes = _completed_1h_closes(history)
        elif tf == "4h":
            closes = _completed_4h_closes(history)
        elif tf == "1d":
            daily = _completed_daily_closes(history)
            closes = daily["close"] if not daily.empty else pd.Series(dtype=float)
        else:
            closes = _completed_weekly_closes(history, ctx.decision_time)

        value = _ema_state(closes, int(self.params["trend_ema_length"]))
        self._trend_cache_key_value = key
        self._trend_cache_value = value
        return value

    def _entry(self, ctx, side, vwap_value, trend_meta):
        reference = float(ctx.current_bar["close"])
        metadata = {
            "research_variant": "vwap_trend_confirmation_htf_v3_selfcontained",
            "source_paper": "Zarattini_Aziz_VWAP_4631351",
            "vwap": float(vwap_value),
            "direction": side,
            "confirmation_bars": int(self.params["confirmation_bars"]),
            "confirmation_count": int(self._streak_count),
            "trend_timeframe": str(self.params["trend_timeframe"]),
            "trend_ema_length": int(self.params["trend_ema_length"]),
            "paper_has_no_stop": True,
        }
        metadata.update(trend_meta)

        return EntrySignal(
            direction=side,
            stop_loss=_safety_stop(
                reference,
                side,
                float(self.params["engine_safety_stop_pct"]),
            ),
            take_profit=None,
            reason="vwap_trend_confirmed_htf",
            metadata=metadata,
        )

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("VWAP trend confirmation HTF v3 requires primary timeframe 1m")

        if ctx.position is None and self._pending_reverse is not None:
            side = self._pending_reverse
            meta = dict(self._pending_meta or {})
            self._pending_reverse = None
            self._pending_meta = None

            today = _today_rth(ctx.bars("1m", count=500))
            if today.empty:
                return None
            vwap_value = _vwap(today)
            if vwap_value is None:
                return None
            return self._entry(ctx, side, vwap_value, meta)

        today = _today_rth(ctx.bars("1m", count=500))
        if today.empty:
            return None

        current = today.iloc[-1]
        ts = pd.Timestamp(current["timestamp"])
        ts = ts.tz_convert(NY) if ts.tzinfo else ts.tz_localize("UTC").tz_convert(NY)

        session_date = ts.date()
        if session_date != self._session_date:
            self._session_date = session_date
            self._streak_side = None
            self._streak_count = 0
            self._pending_reverse = None
            self._pending_meta = None

        minute_number = ts.hour * 60 + ts.minute - 570 + 1
        if minute_number < int(self.params["min_minutes_after_open"]):
            return None

        vwap_value = _vwap(today)
        if vwap_value is None:
            return None

        close = float(current["close"])
        raw_side = "long" if close > vwap_value else "short" if close < vwap_value else None

        allowed = str(self.params["direction"])
        if raw_side is not None and allowed != "both" and raw_side != allowed:
            raw_side = None

        self._update_streak(raw_side)

        required = int(self.params["confirmation_bars"])
        confirmed = (
            self._streak_side
            if self._streak_side is not None and self._streak_count >= required
            else None
        )
        if confirmed is None:
            return None

        # If already in the same confirmed direction, nothing to do and no HTF
        # calculation is needed.
        if ctx.position is not None and confirmed == ctx.position.direction:
            return None

        trend_state, htf_close, htf_ema = self._trend_state(ctx)
        tf = str(self.params["trend_timeframe"])
        trend_allows = tf == "off" or trend_state == confirmed
        trend_meta = {
            "htf_trend_state": trend_state,
            "htf_close": htf_close,
            "htf_ema": htf_ema,
            "htf_filter_passed": bool(trend_allows),
        }

        if ctx.position is not None:
            # Exit on opposite VWAP confirmation regardless of HTF.
            if trend_allows:
                self._pending_reverse = confirmed
                self._pending_meta = trend_meta
            else:
                self._pending_reverse = None
                self._pending_meta = None
            return ExitSignal("vwap_confirmed_reverse")

        if not trend_allows:
            return None

        return self._entry(ctx, confirmed, vwap_value, trend_meta)
