from __future__ import annotations

from app.storage.journal_repository import JournalRepository


MANUAL_SOURCES = {"live_manual", "paper_manual"}
AUTOMATED_SOURCES = {"replay", "backtest"}


class JournalService:
    def __init__(self, repository: JournalRepository):
        self.repository = repository

    def create_trade(self, payload: dict) -> dict:
        data = self._prepare_trade(payload, creating=True)
        return self.repository.create_trade(data)

    def update_trade(self, trade_id: int, payload: dict) -> dict | None:
        current = self.repository.get_trade(trade_id)
        if current is None:
            return None
        merged = {**current, **payload}
        prepared = self._prepare_trade(merged, creating=False)
        changed = {key: prepared[key] for key in prepared if current.get(key) != prepared.get(key)}
        return self.repository.update_trade(trade_id, changed)

    def _prepare_trade(self, payload: dict, *, creating: bool) -> dict:
        data = dict(payload)
        source = str(data.get("source") or "live_manual")
        if source not in MANUAL_SOURCES | AUTOMATED_SOURCES:
            raise ValueError("Unknown trade source")
        data["source"] = source
        ticker = str(data.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError("ticker/pair is required")
        data["ticker"] = ticker
        direction = str(data.get("direction") or "long").lower()
        if direction not in {"long", "short"}:
            raise ValueError("direction must be long or short")
        data["direction"] = direction
        data["fees"] = float(data.get("fees") or 0)
        if data["fees"] < 0:
            raise ValueError("fees cannot be negative")

        # Manual day trades use the user's actual execution price. Position size can
        # be entered as money/notional; quantity is then derived for the maths. The
        # stored quantity is still retained because later broker imports/backtests
        # will naturally supply exact fills/quantities.
        entry = _number(data.get("entry_price"))
        position_amount = _number(data.get("position_amount"))
        quantity = _number(data.get("quantity"))
        if position_amount is not None:
            if position_amount <= 0:
                raise ValueError("position amount must be greater than zero")
            if entry is not None and entry > 0:
                data["quantity"] = position_amount / entry
        elif quantity is not None and quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        data["position_currency"] = str(data.get("position_currency") or "USD").upper()

        # Objective trade maths is derived for both manual and automated sources.
        self._compute_metrics(data)

        closed = bool(data.get("closed_at") or data.get("exit_price") is not None)
        data["status"] = "closed" if closed else "open"
        if creating:
            data.setdefault("name", "Trade")
            data.setdefault("account", "Main")
        return data

    def _compute_metrics(self, data: dict) -> None:
        entry = _number(data.get("entry_price"))
        exit_price = _number(data.get("exit_price"))
        quantity = _number(data.get("quantity"))
        stop = _number(data.get("stop_loss"))
        fees = float(data.get("fees") or 0)
        override = _number(data.get("pnl_override"))
        target = _number(data.get("take_profit"))

        # Planned risk:reward is the plan (target distance / stop distance).
        # Realised R below is based on the actual exit, so a 2:1 planned trade
        # closed halfway to target is correctly +1R, not +2R.
        data["planned_rr"] = _planned_rr(
            entry=entry, stop=stop, target=target, direction=str(data.get("direction") or "long")
        )

        if entry is None or exit_price is None:
            data["result"] = None
            data["result_source"] = None
            data["pnl_amount"] = override
            data["pnl_pct"] = None
            data["r_multiple"] = None
            data["pnl_source"] = "manual_override" if override is not None else None
            return

        mult = 1.0 if data.get("direction") == "long" else -1.0
        move_per_unit = (exit_price - entry) * mult
        gross_pnl = move_per_unit * quantity if quantity is not None else None
        calculated_pnl = gross_pnl - fees if gross_pnl is not None else None
        final_pnl = override if override is not None else calculated_pnl

        data["pnl_amount"] = final_pnl
        data["pnl_source"] = "manual_override" if override is not None else ("computed" if calculated_pnl is not None else None)

        if quantity is not None and entry * quantity != 0 and calculated_pnl is not None:
            data["pnl_pct"] = calculated_pnl / (entry * quantity) * 100
        else:
            data["pnl_pct"] = move_per_unit / entry * 100 if entry else None

        if stop is not None:
            risk_per_unit = abs(entry - stop)
            if risk_per_unit > 1e-12:
                if final_pnl is not None and quantity is not None and quantity > 0:
                    data["r_multiple"] = final_pnl / (risk_per_unit * quantity)
                else:
                    data["r_multiple"] = move_per_unit / risk_per_unit
            else:
                data["r_multiple"] = None
        else:
            data["r_multiple"] = None

        result_basis = final_pnl if final_pnl is not None else move_per_unit
        tolerance = 1e-9
        data["result"] = "win" if result_basis > tolerance else "loss" if result_basis < -tolerance else "breakeven"
        data["result_source"] = "computed"


def _number(value):
    if value in (None, ""):
        return None
    return float(value)


def _planned_rr(*, entry, stop, target, direction):
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    if risk <= 1e-12:
        return None
    if direction == "long":
        if stop >= entry or target <= entry:
            return None
        reward = target - entry
    else:
        if stop <= entry or target >= entry:
            return None
        reward = entry - target
    return reward / risk
