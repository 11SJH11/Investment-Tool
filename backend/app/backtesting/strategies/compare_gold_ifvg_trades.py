"""Compare two Ledger Gold IFVG all-trades CSV exports by SIGNAL identity.

Example:
  python compare_gold_ifvg_trades.py run-209-trades.csv candidate-trades.csv

A trade absent because of a filter is counted as removed; a new trade is added.
BE/early-exit changes are compared for matched signals with changed outcomes.
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path

SIGNAL_TIME = "metadata.ifvg_confirmation_time"
SESSION = "metadata.asia_session_key"


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for row in rows:
        time = row.get(SIGNAL_TIME) or row.get("entry_time") or ""
        session = row.get(SESSION) or ""
        key = (row.get("symbol", ""), session, time, row.get("direction", ""))
        if key in result:
            raise ValueError(f"Duplicate strategy signal {key!r}; inspect CSV")
        result[key] = row
    return result


def r(row):
    return float(row.get("r_multiple") or 0.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="Optional trade-level comparison CSV")
    args = ap.parse_args()
    old, new = read(args.baseline), read(args.candidate)
    matched = old.keys() & new.keys()
    removed = old.keys() - new.keys()
    added = new.keys() - old.keys()
    details = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        details.append({
            "symbol": key[0], "asia_session": key[1], "signal_time": key[2],
            "direction": key[3], "status": "matched" if a and b else ("removed" if a else "added"),
            "baseline_result": a.get("result", "") if a else "",
            "candidate_result": b.get("result", "") if b else "",
            "baseline_r": r(a) if a else "", "candidate_r": r(b) if b else "",
            "delta_r": round((r(b) if b else 0) - (r(a) if a else 0), 6),
        })
    print(f"Baseline:  {len(old):3} trades, {sum(map(r,old.values())):+.2f}R")
    print(f"Candidate: {len(new):3} trades, {sum(map(r,new.values())):+.2f}R")
    print(f"Matched: {len(matched)} | Removed: {len(removed)} | Added: {len(added)}")
    print("Removed original winners:", sum(r(old[k]) > 0 for k in removed))
    print("Removed original losers: ", sum(r(old[k]) < 0 for k in removed))
    print("Removed original BE:     ", sum(r(old[k]) == 0 for k in removed))
    print("Changed matched outcomes:", sum(r(old[k]) != r(new[k]) for k in matched))
    print(f"Difference: {sum(map(r,new.values()))-sum(map(r,old.values())):+.2f}R")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(details[0]) if details else ["status"])
            writer.writeheader()
            writer.writerows(details)
        print("Wrote:", args.out)


if __name__ == "__main__":
    main()
