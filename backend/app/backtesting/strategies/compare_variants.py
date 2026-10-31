#!/usr/bin/env python3
"""Run three IOF-01 hypotheses on the same 1m OHLC CSV.

For real out-of-sample analysis, freeze the settings using a development
period, then rerun this on separate, later data never inspected when tuning.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import pandas as pd

if __package__:
    from .iof01_backtest import Settings, load_bars, run_backtest
else:
    from iof01_backtest import Settings, load_bars, run_backtest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--out", default="iof01_comparison")
    p.add_argument("--spread", type=float, default=0.0)
    p.add_argument("--slippage", type=float, default=0.0)
    p.add_argument("--displacement-atr", type=float, default=2.0)
    p.add_argument("--max-entries", type=int, default=2)
    args=p.parse_args()
    bars=load_bars(args.csv)
    out=Path(args.out)
    out.mkdir(exist_ok=True,parents=True)
    scores=[]
    for variant in ("basic","bos","bos_fvg"):
        cfg=Settings(variant=variant,spread_price=args.spread,
                     slippage_per_side=args.slippage,
                     displacement_atr=args.displacement_atr,
                     max_entries=args.max_entries)
        summary, signals, trades, parts=run_backtest(bars,cfg)
        scores.append({"variant":variant,**summary})
        signals.to_csv(out/f"{variant}_signals.csv",index=False)
        trades.to_csv(out/f"{variant}_trades.csv",index=False)
        parts.to_csv(out/f"{variant}_partial_exits.csv",index=False)
    comparison=pd.DataFrame(scores)
    comparison.to_csv(out/"comparison.csv",index=False)
    print(comparison.to_string(index=False))
    print("Comparison saved:",out.resolve())


if __name__ == "__main__":
    main()
