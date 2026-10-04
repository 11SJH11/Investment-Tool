"""VWAP Trend entry/exit confirmation + VWAP-distance research — Ledger v4.

This file is a deliberately minimal extension of the working
`vwap_trend_confirmation_htf_research_v3` strategy. The VWAP calculation,
higher-timeframe construction, EMA regime filter, safety stop, session handling
and delayed-reversal behaviour are inherited unchanged.

New research controls only:
- `entry_confirmation_bars`: consecutive closes required for a new entry.
- `exit_confirmation_bars`: consecutive opposite closes required to exit.
- `max_entry_vwap_distance_bps`: optional entry/reversal filter; 0 disables it.

Important parity guarantee:
When entry confirmation == exit confirmation and the distance filter is disabled,
`on_bar` deliberately executes the original v3 decision logic verbatim (apart
from reading the renamed entry parameter). This makes E3 / distance=0 the control
for M2/M3/M4 and avoids changing trading semantics merely because v4 exists.

The distance filter is evaluated on the completed signal bar and never blocks an
exit. Ledger run-level controls (max trades/day, cooldown, entry window, leverage,
overnight handling) remain outside the strategy.
"""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo
import math
import pandas as pd

from app.backtesting.models import EntrySignal, ExitSignal
from app.backtesting.strategies.base import ParameterSpec, Strategy, StrategySpec
from app.backtesting.strategies.registry import strategy_registry


KEY = "vwap_trend_entry_exit_distance_research_v4"
NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "direction": "both",
    "entry_confirmation_bars": 3,
    "exit_confirmation_bars": 3,
    "max_entry_vwap_distance_bps": 0.0,  # 0 disables; X25 uses 25
    "min_minutes_after_open": 1,
    "trend_timeframe": "1d",             # current M3 control
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


def _vwap_distance_bps(close, vwap_value):
    close = float(close)
    vwap_value = float(vwap_value)
    if not (math.isfinite(close) and math.isfinite(vwap_value)) or vwap_value <= 0:
        return None
    return abs(close - vwap_value) / vwap_value * 10_000.0


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
class VwapTrendEntryExitDistanceResearchV4(Strategy):
    spec = StrategySpec(
        key=KEY,
        name="VWAP Trend Entry/Exit + Distance · research v4",
        description=(
            "Minimal v3 extension with separate entry/exit confirmation and an "
            "optional maximum entry distance from VWAP."
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
                "entry_confirmation_bars", "Entry confirmation · consecutive closes", "int",
                3, 1, 10, 1,
                help="Use 3 for the current M3/X25/E4/E5 research series.",
            ),
            ParameterSpec(
                "exit_confirmation_bars", "Exit confirmation · opposite closes", "int",
                3, 1, 10, 1,
                help="3 = E3 control, 4 = E4, 5 = E5.",
            ),
            ParameterSpec(
                "max_entry_vwap_distance_bps", "Maximum entry distance from VWAP · bps (0=off)", "float",
                0.0, 0.0, 500.0, 1.0,
                help="0 disables the filter. X25 uses 25 bps.",
            ),
            ParameterSpec(
                "min_minutes_after_open", "Earliest signal · minutes after 09:30", "int",
                1, 1, 120, 1,
            ),
            ParameterSpec(
                "trend_timeframe", "Higher-timeframe trend filter", "choice", "1d",
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
            "Entry": "N completed closes on one side of causal session VWAP.",
            "Exit": "Independent N completed opposite closes; E3 matches v3 control.",
            "VWAP distance": "Optional entry/reversal-only signal-bar filter; 0 disables.",
            "HTF confluence": "New entries/reversals align with completed HTF close vs HTF EMA.",
            "Session": "Force flat at 16:00 with allow_overnight=False.",
            "Stop": "Wide engine-only safety stop; use position-value sizing.",
        },
        source_file="backend/app/backtesting/strategies/vwap_trend_entry_exit_distance_research_v4.py",
    )

    def __init__(self, **params):
        if set(params) - set(DEFAULTS):
            raise ValueError("Unknown VWAP entry/exit/distance parameter")
        super().__init__(**params)

        if str(self.params["direction"]) not in {"both", "long", "short"}:
            raise ValueError("direction must be both, long or short")
        if str(self.params["trend_timeframe"]) not in {"off", "1h", "4h", "1d", "1w"}:
            raise ValueError("trend_timeframe must be off, 1h, 4h, 1d or 1w")

        self.params["entry_confirmation_bars"] = int(self.params["entry_confirmation_bars"])
        self.params["exit_confirmation_bars"] = int(self.params["exit_confirmation_bars"])
        self.params["max_entry_vwap_distance_bps"] = float(self.params["max_entry_vwap_distance_bps"])
        self.params["min_minutes_after_open"] = int(self.params["min_minutes_after_open"])
        self.params["trend_ema_length"] = int(self.params["trend_ema_length"])
        self.params["engine_safety_stop_pct"] = float(self.params["engine_safety_stop_pct"])

        if self.params["entry_confirmation_bars"] < 1:
            raise ValueError("entry_confirmation_bars must be >= 1")
        if self.params["exit_confirmation_bars"] < 1:
            raise ValueError("exit_confirmation_bars must be >= 1")
        if self.params["max_entry_vwap_distance_bps"] < 0:
            raise ValueError("max_entry_vwap_distance_bps cannot be negative")
        if self.params["min_minutes_after_open"] < 1:
            raise ValueError("min_minutes_after_open must be >= 1")
        if self.params["trend_ema_length"] < 1:
            raise ValueError("trend_ema_length must be >= 1")
        if not 0 < self.params["engine_safety_stop_pct"] < 100:
            raise ValueError("engine_safety_stop_pct must be between 0 and 100")

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
        # Keep the working v3 EntrySignal shape/reason/metadata contract.
        reference = float(ctx.current_bar["close"])
        metadata = {
            "research_variant": "vwap_trend_confirmation_htf_v3_selfcontained",
            "source_paper": "Zarattini_Aziz_VWAP_4631351",
            "vwap": float(vwap_value),
            "direction": side,
            "confirmation_bars": int(self.params["entry_confirmation_bars"]),
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

    def _trend_meta(self, ctx, side):
        trend_state, htf_close, htf_ema = self._trend_state(ctx)
        tf = str(self.params["trend_timeframe"])
        trend_allows = tf == "off" or trend_state == side
        return bool(trend_allows), {
            "htf_trend_state": trend_state,
            "htf_close": htf_close,
            "htf_ema": htf_ema,
            "htf_filter_passed": bool(trend_allows),
        }

    def _distance_allows(self, close, vwap_value):
        limit_bps = float(self.params["max_entry_vwap_distance_bps"])
        if limit_bps <= 0.0:
            # Critical for control parity: disabled means no additional calculation
            # or rejection is introduced into the v3 path.
            return True
        distance_bps = _vwap_distance_bps(close, vwap_value)
        return distance_bps is not None and distance_bps <= limit_bps

    def _on_bar_v3_control(self, ctx, vwap_value, close):
        """Original v3 decision logic for E3 / distance-off parity."""
        required = int(self.params["entry_confirmation_bars"])
        confirmed = (
            self._streak_side
            if self._streak_side is not None and self._streak_count >= required
            else None
        )
        if confirmed is None:
            return None

        if ctx.position is not None and confirmed == ctx.position.direction:
            return None

        trend_allows, trend_meta = self._trend_meta(ctx, confirmed)

        if ctx.position is not None:
            if trend_allows:
                self._pending_reverse = confirmed
                self._pending_meta = trend_meta
            else:
                self._pending_reverse = None
                self._pending_meta = None
            # Exact v3 ExitSignal shape: no new metadata or new reason.
            return ExitSignal("vwap_confirmed_reverse")

        if not trend_allows:
            return None

        return self._entry(ctx, confirmed, vwap_value, trend_meta)

    def on_bar(self, ctx):
        if ctx.primary_timeframe != "1m":
            raise ValueError("VWAP trend entry/exit/distance v4 requires primary timeframe 1m")

        # Exact v3 delayed-reversal structure.
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

        entry_required = int(self.params["entry_confirmation_bars"])
        exit_required = int(self.params["exit_confirmation_bars"])
        distance_limit = float(self.params["max_entry_vwap_distance_bps"])

        # Strong parity path: this is the M2/M3/M4/E3 control configuration.
        if entry_required == exit_required and distance_limit <= 0.0:
            return self._on_bar_v3_control(ctx, vwap_value, close)

        # ---- Position management for E4/E5 and/or distance-filter variants ----
        if ctx.position is not None:
            if self._streak_side is None or self._streak_side == ctx.position.direction:
                return None
            if self._streak_count < exit_required:
                return None

            reverse_side = self._streak_side

            # Exits are unconditional once exit confirmation is reached. Filters
            # only determine whether a delayed reverse entry may be queued.
            if self._streak_count >= entry_required:
                trend_allows, trend_meta = self._trend_meta(ctx, reverse_side)
                if trend_allows and self._distance_allows(close, vwap_value):
                    self._pending_reverse = reverse_side
                    self._pending_meta = trend_meta
                else:
                    self._pending_reverse = None
                    self._pending_meta = None
            else:
                self._pending_reverse = None
                self._pending_meta = None

            # Keep v3's supported ExitSignal contract.
            return ExitSignal("vwap_confirmed_reverse")

        # ---- Flat entry ----
        if self._streak_side is None or self._streak_count < entry_required:
            return None

        entry_side = self._streak_side
        trend_allows, trend_meta = self._trend_meta(ctx, entry_side)
        if not trend_allows:
            return None
        if not self._distance_allows(close, vwap_value):
            return None

        return self._entry(ctx, entry_side, vwap_value, trend_meta)
