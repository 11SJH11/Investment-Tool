#!/usr/bin/env python3
"""IOF-01: displacement-zone retest RESEARCH backtest (not a trading bot).

Requires: pandas, numpy

Inputs: sorted or unsorted 1-minute CSV with time/timestamp, open, high, low, close.
Output: signal summaries, partial fills, trades, and cumulative risk units (R).

Does NOT detect actual institutional orders, submit orders, or connect to MT5.
Positions and signals are simulated from completed OHLC candles only.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Settings:
    variant: str = "bos"               # basic | bos | bos_fvg
    atr_period: int = 14
    displacement_atr: float = 2.0
    impulse_max_bars: int = 3
    candle_body_min: float = 0.60
    swing_lookback: int = 20
    base_lookback: int = 5
    zone_max_atr: float = 1.50
    stop_buffer_atr: float = 0.10
    max_stop_atr: float = 3.0
    signal_expiry_bars: int = 90        # how long an unfilled order is live
    max_holding_bars: int = 0          # 0 = no time exit (until TP2/SL/EOD)
    max_entries: int = 2               # 1 campaign risk budget split equally
    rearm_distance_atr: float = 0.50  # leave zone before another revisit
    tp1_r: float = 1.0
    tp2_r: float = 2.0
    tp3_r: float = 3.0
    close_at_tp1: float = 0.30
    close_at_tp2: float = 0.30
    # remaining 40% stays open until TP3 / break-even / max hold
    spread_price: float = 0.0         # gold $/oz roundtrip spread estimate
    slippage_per_side: float = 0.0   # gold $/oz per fill, entry and exit

    def validate(self) -> None:
        if self.variant not in {"basic", "bos", "bos_fvg"}:
            raise ValueError("variant must be basic, bos, or bos_fvg")
        if min(self.atr_period, self.impulse_max_bars, self.swing_lookback,
               self.base_lookback, self.signal_expiry_bars,
               self.max_entries) < 1:
            raise ValueError("Bar periods and max_entries must be positive")
        if self.max_holding_bars < 0:
            raise ValueError("max_holding_bars must be >= 0")
        if not (0 <= self.candle_body_min <= 1):
            raise ValueError("candle_body_min must be in [0, 1]")
        if not (0 <= self.close_at_tp1 <= 1 and 0 <= self.close_at_tp2 <= 1
                and self.close_at_tp1 + self.close_at_tp2 <= 1):
            raise ValueError("Partial closes must be between 0 and 1 and sum <= 1")
        if not (0 < self.tp1_r < self.tp2_r < self.tp3_r):
            raise ValueError("Need 0 < TP1 R < TP2 R < TP3 R")
        if min(self.displacement_atr, self.zone_max_atr, self.max_stop_atr) <= 0:
            raise ValueError("ATR thresholds must be positive")
        if min(self.stop_buffer_atr, self.rearm_distance_atr,
               self.spread_price, self.slippage_per_side) < 0:
            raise ValueError("Buffers and execution costs must be nonnegative")


@dataclass
class Leg:
    number: int
    entered_i: int
    entry: float
    initial_stop: float
    remaining: float = 1.0
    tp1_done: bool = False
    tp2_done: bool = False
    exit_r: float = 0.0
    exit_parts: list = field(default_factory=list)


@dataclass
class Signal:
    signal_id: int
    detected_i: int
    direction: int                 # +1 long, -1 short
    zone_low: float
    zone_high: float
    entry: float
    initial_stop: float
    atr: float
    base_i: int
    impulse_bars: int
    displacement_in_atr: float
    bos: bool
    fvg: bool
    status: str = "ACTIVE"
    legs: list[Leg] = field(default_factory=list)
    armed: bool = True
    last_entry_i: int = -1
    ambiguous_bars: int = 0
    finished_i: Optional[int] = None

    @property
    def distance(self) -> float:
        return abs(self.entry - self.initial_stop)

    def target(self, r: float) -> float:
        return self.entry + self.direction * r * self.distance



def load_bars(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [str(x).strip().lower() for x in df.columns]
    names = {"datetime": "time", "date": "time", "timestamp": "time",
             "o": "open", "h": "high", "l": "low", "c": "close"}
    df = df.rename(columns={k: v for k, v in names.items() if k in df and v not in df})
    required = {"time", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"CSV needs columns {sorted(required)}; got {list(df.columns)}")
    for name in ["open", "high", "low", "close"]:
        df[name] = pd.to_numeric(df[name], errors="raise")
    if pd.api.types.is_numeric_dtype(df["time"]):
        unit = "ms" if df["time"].iloc[0] > 1e11 else "s"
        df["time"] = pd.to_datetime(df["time"], unit=unit, utc=True, errors="raise")
    else:
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="raise")
    df = df.sort_values("time").reset_index(drop=True)
    if df.empty or df["time"].isna().any() or df["time"].duplicated().any():
        raise ValueError("CSV timestamps must be present and unique")
    if not np.isfinite(df[["open", "high", "low", "close"]].to_numpy()).all():
        raise ValueError("OHLC must be finite numeric values")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) |
        (df["low"] > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("Invalid OHLC: high/low inconsistent with open/close")
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    # ATR based ONLY on candles completed before detection candle i.
    df["atr_previous"] = (true_range.ewm(alpha=1 / 14, adjust=False,
                                        min_periods=14).mean().shift(1))
    return df


def prepare(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Calculate prior-bar Wilder-style ATR for chosen settings."""
    df = df.copy()
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    df["atr_previous"] = (tr.ewm(alpha=1 / settings.atr_period, adjust=False,
                                 min_periods=settings.atr_period).mean().shift(1))
    return df


def make_candidate(df: pd.DataFrame, i: int, cfg: Settings, sid: int) -> Optional[Signal]:
    """Causal signal creation: evaluate only bars <= i, at close of bar i."""
    if i < cfg.swing_lookback + cfg.impulse_max_bars + cfg.base_lookback + 2:
        return None
    atr = float(df.at[i, "atr_previous"])
    if not np.isfinite(atr) or atr <= 0:
        return None
    o, c, h, l = (float(df.at[i, x]) for x in ("open", "close", "high", "low"))
    body_ratio = abs(c - o) / max(h - l, 1e-12)
    if body_ratio < cfg.candle_body_min or c == o:
        return None
    direction = 1 if c > o else -1
    for k in range(1, cfg.impulse_max_bars + 1):
        start = i - k + 1
        move = direction * (c - float(df.at[start, "open"]))
        displacement_in_atr = move / atr
        if displacement_in_atr < cfg.displacement_atr:
            continue
        prior = df.iloc[start - cfg.swing_lookback:start]
        if len(prior) < cfg.swing_lookback:
            continue
        bos = (c > float(prior["high"].max()) if direction == 1
               else c < float(prior["low"].min()))
        fvg = (float(df.at[i, "low"]) > float(df.at[i - 2, "high"])
               if direction == 1 else
               float(df.at[i, "high"]) < float(df.at[i - 2, "low"]))
        if cfg.variant in {"bos", "bos_fvg"} and not bos:
            continue
        if cfg.variant == "bos_fvg" and not fvg:
            continue
        for base in range(start - 1, max(0, start - cfg.base_lookback) - 1, -1):
            bo, bc = float(df.at[base, "open"]), float(df.at[base, "close"])
            if direction * (bc - bo) >= 0:
                continue                   # last opposing candle
            low = float(df.at[base, "low"])
            high = float(df.at[base, "high"])
            if high - low > cfg.zone_max_atr * atr:
                continue
            entry = high if direction == 1 else low
            stop = low - cfg.stop_buffer_atr * atr if direction == 1 else high + cfg.stop_buffer_atr * atr
            distance = abs(entry - stop)
            if distance <= 0 or distance > cfg.max_stop_atr * atr:
                continue
            # Ignore already-touched zones while the impulse formed: not fresh.
            between = df.iloc[base + 1:i + 1]
            if direction == 1 and (between["low"] <= entry).any():
                # Exempt early breakout candles still in/near base by checking
                # only after displacement begins; retests after creation are future bars.
                impulse = df.iloc[start:i + 1]
                if (impulse["close"] <= entry).any():
                    continue
            if direction == -1 and (between["high"] >= entry).any():
                impulse = df.iloc[start:i + 1]
                if (impulse["close"] >= entry).any():
                    continue
            return Signal(sid, i, direction, low, high, entry, stop, atr,
                          base, k, displacement_in_atr, bos, fvg)
    return None


def level_touched(bar: pd.Series, level: float, direction: int) -> bool:
    """Hit a favorable objective for the given direction."""
    return float(bar.high) >= level if direction == 1 else float(bar.low) <= level


def stopped(bar: pd.Series, level: float, direction: int) -> bool:
    return float(bar.low) <= level if direction == 1 else float(bar.high) >= level


def gap_stop_fill(bar: pd.Series, stop: float, direction: int) -> float:
    # Stop orders can slip beyond the level on a price gap.
    return min(float(bar.open), stop) if direction == 1 else max(float(bar.open), stop)


def exit_part(sig: Signal, leg: Leg, fraction: float, price: float, tag: str,
              i: int, df: pd.DataFrame, cfg: Settings, parts: list) -> None:
    fraction = min(fraction, leg.remaining)
    if fraction <= 1e-9:
        return
    # 1R denotes the TOTAL campaign's initial risk budget, divided across entries.
    allocation = 1 / cfg.max_entries
    gross_r = fraction * allocation * sig.direction * (price - leg.entry) / sig.distance
    # Mid-OHLC model: charge effective full round-trip friction per exited fraction.
    costs_r = (fraction * allocation *
               (cfg.spread_price + 2 * cfg.slippage_per_side) / sig.distance)
    net_r = gross_r - costs_r
    leg.exit_r += net_r
    leg.remaining = max(0.0, leg.remaining - fraction)
    row = {"signal_id": sig.signal_id, "leg": leg.number,
           "direction": "LONG" if sig.direction == 1 else "SHORT",
           "entry_time": str(df.at[leg.entered_i, "time"]),
           "exit_time": str(df.at[i, "time"]), "entry_price": leg.entry,
           "exit_price": price, "fraction_of_leg": fraction,
           "exit_reason": tag, "gross_r": gross_r, "cost_r": costs_r,
           "net_r": net_r}
    parts.append(row)
    leg.exit_parts.append(tag)


def run_backtest(input_df: pd.DataFrame, cfg: Settings):
    cfg.validate()
    df = prepare(input_df, cfg)
    signals: list[Signal] = []
    partials: list[dict] = []
    active: Optional[Signal] = None
    last_base: set[tuple[int, int]] = set()

    for i in range(len(df)):
        bar = df.iloc[i]
        if active is not None and i > active.detected_i:
            s = active
            living = [x for x in s.legs if x.remaining > 1e-9]
            age_from_first_entry = i - s.legs[0].entered_i if s.legs else 0

            # Original SL cancels the entire signal BEFORE TP2. The pessimistic
            # same-bar ordering is SL first even when TP2 is also reached.
            if s.status == "ACTIVE" and stopped(bar, s.initial_stop, s.direction):
                valid_armed_order = (s.armed and len(s.legs) < cfg.max_entries and
                                     (bool(s.legs) or i - s.detected_i <= cfg.signal_expiry_bars))
                open_not_beyond_stop = (float(bar.open) > s.initial_stop
                                        if s.direction == 1 else
                                        float(bar.open) < s.initial_stop)
                if valid_armed_order and open_not_beyond_stop:
                    # Price crosses a resting limit AND SL in one candle.
                    # Assume entry was filled first, and THEN stopped.
                    # This applies to re-entries too, not just the first entry.
                    s.legs.append(Leg(len(s.legs) + 1, i, s.entry, s.initial_stop))
                for leg in s.legs:
                    if leg.remaining > 1e-9:
                        exit_part(s, leg, leg.remaining,
                                  gap_stop_fill(bar, s.initial_stop, s.direction),
                                  "INITIAL_SL", i, df, cfg, partials)
                s.status, s.finished_i = "SL", i

            elif s.status == "ACTIVE":
                # All existing positions can take partial profits, with their
                # ORIGINAL stop intact until the shared campaign hits TP2.
                hit_tp2 = level_touched(bar, s.target(cfg.tp2_r), s.direction)
                if s.legs:
                    for leg in living:
                        if not leg.tp1_done and level_touched(bar, s.target(cfg.tp1_r), s.direction):
                            exit_part(s, leg, cfg.close_at_tp1, s.target(cfg.tp1_r),
                                      "TP1", i, df, cfg, partials)
                            leg.tp1_done = True
                        if not leg.tp2_done and hit_tp2:
                            exit_part(s, leg, cfg.close_at_tp2, s.target(cfg.tp2_r),
                                      "TP2", i, df, cfg, partials)
                            leg.tp2_done = True
                if hit_tp2:
                    s.status = "TP2"
                    # Ambiguous: after TP2 and SL -> BE, bar could revisit BE
                    # before/after reaching TP3. Resolve against the strategy.
                    for leg in s.legs:
                        if leg.remaining <= 1e-9:
                            continue
                        if stopped(bar, leg.entry, s.direction):
                            exit_part(s, leg, leg.remaining, leg.entry, "BE_SAME_BAR",
                                      i, df, cfg, partials)
                            s.ambiguous_bars += 1
                        elif level_touched(bar, s.target(cfg.tp3_r), s.direction):
                            exit_part(s, leg, leg.remaining, s.target(cfg.tp3_r),
                                      "TP3", i, df, cfg, partials)
                    if not s.legs:
                        s.finished_i = i     # TP2 reached without any entry
                else:
                    # A visit from above/below a resting zone-edge limit.
                    # Same-bar TP credit isn't taken for new entries.
                    can_enter = (s.armed and len(s.legs) < cfg.max_entries and
                                 (bool(s.legs) or i - s.detected_i <= cfg.signal_expiry_bars))
                    touched_entry = (float(bar.low) <= s.entry if s.direction == 1
                                     else float(bar.high) >= s.entry)
                    if can_enter and touched_entry:
                        s.legs.append(Leg(len(s.legs) + 1, i, s.entry, s.initial_stop))
                        s.last_entry_i, s.armed = i, False
                    if not s.armed and s.last_entry_i < i:
                        reset = cfg.rearm_distance_atr * s.atr
                        if ((s.direction == 1 and float(bar.close) > s.zone_high + reset)
                            or (s.direction == -1 and float(bar.close) < s.zone_low - reset)):
                            s.armed = True
                    if not s.legs and i - s.detected_i >= cfg.signal_expiry_bars:
                        s.status, s.finished_i = "EXPIRED", i

            elif s.status == "TP2":
                for leg in living:
                    if stopped(bar, leg.entry, s.direction):
                        exit_part(s, leg, leg.remaining,
                                  gap_stop_fill(bar, leg.entry, s.direction),
                                  "BREAKEVEN_STOP", i, df, cfg, partials)
                    elif level_touched(bar, s.target(cfg.tp3_r), s.direction):
                        exit_part(s, leg, leg.remaining, s.target(cfg.tp3_r),
                                  "TP3", i, df, cfg, partials)

            if (cfg.max_holding_bars > 0 and s.status in {"ACTIVE", "TP2"}
                and s.legs and age_from_first_entry >= cfg.max_holding_bars):
                for leg in s.legs:
                    if leg.remaining > 1e-9:
                        exit_part(s, leg, leg.remaining, float(bar.close),
                                  "MAX_HOLD", i, df, cfg, partials)
                s.status, s.finished_i = "MAX_HOLD", i
            if s.status == "TP2" and all(leg.remaining <= 1e-9 for leg in s.legs):
                s.finished_i = i
            if s.status in {"SL", "EXPIRED", "MAX_HOLD"} or (s.status == "TP2" and s.finished_i is not None):
                active = None

        # Only one simultaneous signal/campaign. Signal seen at close i,
        # so first possible fill is the NEXT candle.
        if active is None:
            c = make_candidate(df, i, cfg, len(signals) + 1)
            if c is not None and (c.base_i, c.direction) not in last_base:
                signals.append(c)
                last_base.add((c.base_i, c.direction))
                active = c

    # Mark-to-market remaining open positions at final close, without claiming
    # a target or fabricating an artificial final stop.
    if active is not None:
        end = len(df) - 1
        for leg in active.legs:
            if leg.remaining > 1e-9:
                exit_part(active, leg, leg.remaining, float(df.at[end, "close"]),
                          "END_OF_DATA", end, df, cfg, partials)
        active.status, active.finished_i = "END_OF_DATA", end

    signal_rows = []
    trades = []
    for s in signals:
        combined_r = sum(l.exit_r for l in s.legs)
        signal_rows.append({
            "signal_id": s.signal_id, "detected_time": str(df.at[s.detected_i, "time"]),
            "finished_time": str(df.at[s.finished_i, "time"]) if s.finished_i is not None else "",
            "direction": "LONG" if s.direction == 1 else "SHORT",
            "variant": cfg.variant, "status": s.status,
            "base_time": str(df.at[s.base_i, "time"]), "zone_low": s.zone_low,
            "zone_high": s.zone_high, "entry": s.entry, "original_sl": s.initial_stop,
            "tp1": s.target(cfg.tp1_r), "tp2": s.target(cfg.tp2_r),
            "tp3": s.target(cfg.tp3_r), "displacement_atr": s.displacement_in_atr,
            "impulse_bars": s.impulse_bars, "bos": s.bos, "fvg": s.fvg,
            "entries": len(s.legs), "campaign_net_r": combined_r,
            "ambiguous_bars": s.ambiguous_bars,
        })
        for l in s.legs:
            trades.append({"signal_id": s.signal_id, "leg": l.number,
                           "entry_time": str(df.at[l.entered_i, "time"]),
                           "direction": "LONG" if s.direction == 1 else "SHORT",
                           "entry": l.entry, "initial_sl": l.initial_stop,
                           "exit_events": ";".join(l.exit_parts), "net_campaign_r": l.exit_r})

    signal_out = pd.DataFrame(signal_rows)
    parts_out = pd.DataFrame(partials)
    trades_out = pd.DataFrame(trades)
    filled = signal_out.loc[signal_out["entries"] > 0] if not signal_out.empty else signal_out
    r = filled["campaign_net_r"] if not filled.empty else pd.Series(dtype=float)
    curve = r.cumsum()
    dd = (curve - curve.cummax().clip(lower=0)) if not curve.empty else pd.Series(dtype=float)
    results = {
        "bars": len(df), "signals": len(signals),
        "filled_campaigns": len(filled), "entry_legs": len(trades),
        "winning_campaign_pct": round(100 * float((r > 0).mean()), 2) if len(r) else None,
        "total_r": round(float(r.sum()), 4),
        "avg_r_per_filled_campaign": round(float(r.mean()), 4) if len(r) else None,
        "max_drawdown_r_closed_campaigns": round(float(dd.min()), 4) if len(dd) else 0.0,
        "ambiguous_tp2_be_bars": sum(s.ambiguous_bars for s in signals),
        "zero_execution_costs": cfg.spread_price == 0 and cfg.slippage_per_side == 0,
        "important": "Research approximation; not a verified strategy; OHLC and execution approximations apply."
    }
    return results, signal_out, trades_out, parts_out


def main() -> None:
    parser = argparse.ArgumentParser(description="IOF-01 historical-only research backtest")
    parser.add_argument("csv", help="1-minute OHLC CSV with time/open/high/low/close")
    parser.add_argument("--variant", choices=["basic", "bos", "bos_fvg"], default="bos")
    parser.add_argument("--out", default="iof01_results", help="Output directory")
    parser.add_argument("--spread", type=float, default=0.0, help="Estimated round-trip spread in $/oz")
    parser.add_argument("--slippage", type=float, default=0.0, help="Estimated slippage per fill in $/oz")
    parser.add_argument("--max-entries", type=int, default=2)
    parser.add_argument("--displacement-atr", type=float, default=2.0)
    parser.add_argument("--expiry-bars", type=int, default=90)
    parser.add_argument("--max-holding-bars", type=int, default=0,
                        help="Optional forced time exit; 0 disables it")
    args = parser.parse_args()
    cfg = Settings(variant=args.variant, spread_price=args.spread,
                   slippage_per_side=args.slippage, max_entries=args.max_entries,
                   displacement_atr=args.displacement_atr,
                   signal_expiry_bars=args.expiry_bars,
                   max_holding_bars=args.max_holding_bars)
    bars = load_bars(args.csv)
    summary, signals, trades, partials = run_backtest(bars, cfg)
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    signals.to_csv(dest / "signals.csv", index=False)
    trades.to_csv(dest / "trades.csv", index=False)
    partials.to_csv(dest / "partial_exits.csv", index=False)
    (dest / "summary.json").write_text(json.dumps({"settings": asdict(cfg), "results": summary},
                                                    indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved CSV + JSON files to {dest.resolve()}")


if __name__ == "__main__":
    main()
