"""
portfolio.py

Tracks your holdings, contributions, and target allocation.
Nothing here ever touches real money or brokerage accounts -- this is
purely a record-keeping and analysis layer. You still execute any trades
yourself.

Note and exit_condition now live directly on each Contribution -- when you
log a buy, you write your reasoning at the same time, in the same place.
No network/fetching logic lives here; main.py handles pulling prices and
passes them in, keeping this module pure and easy to test.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Dict, List, Optional


STATE_FILE = os.path.join(os.path.dirname(__file__), "portfolio_state.json")


@dataclass
class Contribution:
    date: str              # ISO date string -- when you actually bought it
    ticker: str
    amount: float           # dollars contributed
    shares: float             # shares bought at the time
    price: float               # price per share at time of purchase
    note: str = ""               # your reasoning/thesis, written at the same time you log the buy
    exit_condition: str = ""       # e.g. "Sell if debt/equity exceeds 100" -- optional, checkable by the AI agent


@dataclass
class JournalEntry:
    """Legacy standalone journal entries from before notes were merged into
    Contribution directly. Kept only so old saved state still loads without
    losing data -- new entries should go on Contribution.note instead."""
    date: str
    ticker: str
    note: str
    exit_condition: str = ""


@dataclass
class Portfolio:
    target_allocation: Dict[str, float] = field(default_factory=dict)  # ticker -> target % (0-1)
    contributions: List[Contribution] = field(default_factory=list)
    journal: List[JournalEntry] = field(default_factory=list)  # legacy, see JournalEntry docstring

    def add_journal_entry(self, ticker: str, note: str, exit_condition: str = "", on_date: str = None):
        """Kept for backward compatibility. New code should attach note/exit_condition
        directly on add_contribution instead."""
        on_date = on_date or date.today().isoformat()
        self.journal.append(JournalEntry(date=on_date, ticker=ticker, note=note, exit_condition=exit_condition))

    def set_target_allocation(self, allocation: Dict[str, float]):
        total = sum(allocation.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Target allocation must sum to 1.0, got {total:.3f}")
        self.target_allocation = allocation

    def add_contribution(self, ticker: str, amount: float, price: float, on_date: str = None,
                          note: str = "", exit_condition: str = ""):
        on_date = on_date or date.today().isoformat()
        shares = amount / price
        self.contributions.append(Contribution(
            date=on_date, ticker=ticker, amount=amount, shares=shares, price=price,
            note=note, exit_condition=exit_condition,
        ))

    def holdings_summary(self) -> Dict[str, Dict[str, float]]:
        """Returns {ticker: {'shares': x, 'invested': y}} -- aggregated across all buys of that ticker."""
        summary = {}
        for c in self.contributions:
            if c.ticker not in summary:
                summary[c.ticker] = {"shares": 0.0, "invested": 0.0}
            summary[c.ticker]["shares"] += c.shares
            summary[c.ticker]["invested"] += c.amount
        return summary

    def current_value(self, latest_prices: Dict[str, float]) -> Dict[str, Dict[str, float]]:
        """
        Given a dict of {ticker: current_price}, returns per-ticker value,
        gain/loss, and current allocation percentages (aggregated across all
        buys of that ticker -- see contributions_detail() for per-transaction).
        """
        summary = self.holdings_summary()
        total_value = 0.0
        result = {}
        for ticker, h in summary.items():
            price = latest_prices.get(ticker)
            if price is None:
                continue
            value = h["shares"] * price
            total_value += value
            result[ticker] = {
                "shares": h["shares"],
                "invested": h["invested"],
                "value": value,
                "gain_loss": value - h["invested"],
                "gain_loss_pct": (value - h["invested"]) / h["invested"] * 100 if h["invested"] else 0,
            }
        for ticker in result:
            result[ticker]["current_allocation_pct"] = (
                result[ticker]["value"] / total_value * 100 if total_value else 0
            )
        return result

    def contributions_detail(self, latest_prices: Dict[str, float]) -> List[dict]:
        """
        Per-transaction detail (NOT aggregated by ticker): each individual
        logged buy, with the price you paid then vs. the current price now,
        plus your note/exit_condition from when you logged it. Sorted most
        recent first.
        """
        result = []
        for c in self.contributions:
            current_price = latest_prices.get(c.ticker)
            current_value = c.shares * current_price if current_price is not None else None
            gain_loss = (current_value - c.amount) if current_value is not None else None
            gain_loss_pct = (gain_loss / c.amount * 100) if gain_loss is not None and c.amount else None
            result.append({
                "date": c.date,
                "ticker": c.ticker,
                "amount": c.amount,
                "shares": c.shares,
                "price_paid": c.price,
                "price_now": current_price,
                "current_value": current_value,
                "gain_loss": gain_loss,
                "gain_loss_pct": gain_loss_pct,
                "note": c.note,
                "exit_condition": c.exit_condition,
            })
        result.sort(key=lambda x: x["date"], reverse=True)
        return result

    def rebalance_suggestions(self, latest_prices: Dict[str, float], drift_threshold_pct: float = 5.0):
        """
        Compares current allocation to target and flags tickers that have
        drifted beyond the threshold (in percentage points).
        """
        current = self.current_value(latest_prices)
        suggestions = []
        for ticker, target_pct in self.target_allocation.items():
            actual_pct = current.get(ticker, {}).get("current_allocation_pct", 0) / 100
            drift = (actual_pct - target_pct) * 100
            if abs(drift) >= drift_threshold_pct:
                direction = "overweight" if drift > 0 else "underweight"
                suggestions.append({
                    "ticker": ticker,
                    "target_pct": target_pct * 100,
                    "actual_pct": actual_pct * 100,
                    "drift_pct": drift,
                    "direction": direction,
                })
        return suggestions

    def next_contribution_plan(self, amount: float) -> Dict[str, float]:
        """
        Given a new amount to invest, splits it according to target allocation.
        Simple version -- doesn't yet account for correcting existing drift.
        """
        return {ticker: round(amount * pct, 2) for ticker, pct in self.target_allocation.items()}

    def save(self, path: str = STATE_FILE):
        data = {
            "target_allocation": self.target_allocation,
            "contributions": [asdict(c) for c in self.contributions],
            "journal": [asdict(j) for j in self.journal],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str = STATE_FILE) -> "Portfolio":
        if not os.path.exists(path):
            return cls()
        with open(path) as f:
            data = json.load(f)
        p = cls(target_allocation=data.get("target_allocation", {}))
        # Old saved contributions won't have note/exit_condition keys -- default them in.
        raw_contribs = data.get("contributions", [])
        for c in raw_contribs:
            c.setdefault("note", "")
            c.setdefault("exit_condition", "")
        p.contributions = [Contribution(**c) for c in raw_contribs]
        p.journal = [JournalEntry(**j) for j in data.get("journal", [])]
        return p
