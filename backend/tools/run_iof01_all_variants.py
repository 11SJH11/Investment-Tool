#!/usr/bin/env python3
"""Run ORIGINAL IOF-01 Basic/BOS/BOS+FVG against the SAME exported 1m CSV.

This preserves two-entry campaign accounting and OHLC partial-fill assumptions
from the uploaded reference, unlike the Ledger-native single-entry proxy.
Read-only: consumes a CSV and writes only reports into --out.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from iof01_reference_backtest import Settings, load_bars, run_backtest

VARIANTS = ("basic", "bos", "bos_fvg")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("csv", help="Exported Ledger OHLC 1m CSV with UTC timestamps")
    p.add_argument("--out", default="iof01_comparison")
    p.add_argument("--spread", type=float, default=0.0, help="Full estimated spread in PRICE units")
    p.add_argument("--slippage", type=float, default=0.0, help="Slippage per side, PRICE units")
    p.add_argument("--max-entries", type=int, default=2)
    p.add_argument("--displacement-atr", type=float, default=2.0)
    p.add_argument("--expiry-bars", type=int, default=90)
    p.add_argument("--max-holding-bars", type=int, default=0)
    args = p.parse_args()
    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    bars = load_bars(args.csv)
    rows = []
    for variant in VARIANTS:
        config = Settings(variant=variant, spread_price=args.spread,
                          slippage_per_side=args.slippage,
                          max_entries=args.max_entries,
                          displacement_atr=args.displacement_atr,
                          signal_expiry_bars=args.expiry_bars,
                          max_holding_bars=args.max_holding_bars)
        summary, signals, trades, partials = run_backtest(bars, config)
        folder = out / variant
        folder.mkdir(exist_ok=True)
        signals.to_csv(folder / "signals.csv", index=False)
        trades.to_csv(folder / "trades.csv", index=False)
        partials.to_csv(folder / "partial_exits.csv", index=False)
        (folder / "summary.json").write_text(
            json.dumps({"settings": asdict(config), "results": summary}, indent=2),
            encoding="utf-8")
        rows.append({"variant": variant, **summary})
    comparison = pd.DataFrame(rows)
    comparison.to_csv(out / "comparison.csv", index=False)
    (out / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(comparison[["variant", "signals", "filled_campaigns", "entry_legs",
                      "winning_campaign_pct", "total_r",
                      "max_drawdown_r_closed_campaigns"]].to_string(index=False))
    print(f"Results: {out}")
    print("Original research model. Intrabar OHLC sequencing and zero-cost defaults can overstate results.")


if __name__ == "__main__":
    main()
