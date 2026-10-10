#!/usr/bin/env python3
"""Export immutable Ledger saved-run trades and summary without rendering PDFs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.storage.database import Database
from app.storage.backtest_run_repository import BacktestRunRepository


def flatten_trade(trade: dict, index: int) -> dict:
    row = {
        "trade_number": index + 1,
        **{k: v for k, v in trade.items() if k != "metadata"},
    }
    metadata = trade.get("metadata") or {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            row[f"metadata.{key}"] = value
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, nargs="+", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("research_output"))
    args = parser.parse_args()

    settings = get_settings()
    repo = BacktestRunRepository(Database(settings.database_path))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    for run_id in args.run_id:
        run = repo.get(run_id)
        result = run.get("result") or {}
        trades = result.get("trades") or []
        config = run.get("config") or {}
        strategy = result.get("strategy") or {}

        trades_path = args.out_dir / f"run-{run_id}-trades.csv"
        pd.DataFrame(
            [flatten_trade(trade, i) for i, trade in enumerate(trades)]
        ).to_csv(trades_path, index=False, encoding="utf-8")

        summary = {
            "run_id": run_id,
            "name": run.get("name"),
            "test_role": run.get("test_role"),
            "start_date": run.get("start_date"),
            "end_date": run.get("end_date"),
            "strategy": strategy,
            "config": config,
            "metrics": result.get("metrics") or {},
            "symbols": result.get("symbols") or run.get("symbols"),
            "primary_timeframe": result.get("primary_timeframe"),
            "session": result.get("session"),
            "trade_count_saved": len(trades),
        }
        summary_path = args.out_dir / f"run-{run_id}-summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )

        print(f"Run {run_id}:")
        print(f"  {trades_path.resolve()}")
        print(f"  {summary_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
