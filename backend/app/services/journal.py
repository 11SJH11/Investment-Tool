from __future__ import annotations

from datetime import datetime, timezone
import math

from app.storage.journal_repository import JournalRepository
from app.core.journal_fields import REVIEW_FIELDS
from app.data.futures import execution_economics, execution_contract
from app.data.instruments import instrument_spec


MANUAL_SOURCES = {"live_manual", "paper_manual"}
AUTOMATED_SOURCES = {"replay", "backtest"}


class JournalService:
    def __init__(self, repository: JournalRepository):
        self.repository = repository

    def create_trade(self, payload: dict) -> dict:
        data = self._prepare_trade(payload, creating=True)
        external_id = str(data.get("external_id") or "").strip()
        if external_id:
            existing = self.repository.get_by_external(
                source=data["source"],
                external_provider=str(data.get("external_provider") or ""),
                external_id=external_id,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
        return self.repository.create_trade(data)

    def update_trade(self, trade_id: int, payload: dict) -> dict | None:
        current = self.repository.get_trade(trade_id)
        if current is None:
            return None
        if str(current["source"]).startswith("broker_"):
            if set(payload) - REVIEW_FIELDS:
                raise ValueError("Broker execution facts and source metadata are read-only")
            self._validate_review(payload)
            return self.repository.update_trade(trade_id, payload)
        if str(payload.get("source") or "").startswith("broker_"):
            raise ValueError("Use broker sync to import broker trades")
        if set(payload) <= REVIEW_FIELDS:
            self._validate_review(payload)
            return self.repository.update_trade(trade_id, payload)
        merged = {**current, **payload}
        prepared = self._prepare_trade(merged, creating=False)
        changed = {key: prepared[key] for key in prepared if current.get(key) != prepared.get(key)}
        return self.repository.update_trade(trade_id, changed)

    def _prepare_trade(self, payload: dict, *, creating: bool) -> dict:
        data = dict(payload)
        self._validate_review(data)
        for key in ("opened_at", "closed_at"):
            if data.get(key):
                try:
                    stamp = datetime.fromisoformat(str(data[key]).replace("Z", "+00:00"))
                    data[key] = (stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
                except ValueError:
                    raise ValueError(f"{key} must be an ISO timestamp") from None
        if data.get("opened_at") and data.get("closed_at") and datetime.fromisoformat(data["closed_at"]) < datetime.fromisoformat(data["opened_at"]):
            raise ValueError("Exit time cannot precede entry time")
        source = str(data.get("source") or "live_manual")
        if source not in MANUAL_SOURCES | AUTOMATED_SOURCES and not source.startswith("broker_"):
            raise ValueError("Unknown trade source")
        data["source"] = source

        external_provider = str(data.get("external_provider") or "").strip().lower()
        external_id = str(data.get("external_id") or "").strip()
        external_order_id = str(data.get("external_order_id") or "").strip()
        source_metadata = data.get("source_metadata") or {}
        if not isinstance(source_metadata, dict):
            raise ValueError("source_metadata must be an object")
        if source.startswith("broker_"):
            external_provider = external_provider or source.removeprefix("broker_")
            if not external_provider or not external_id:
                raise ValueError("broker imports require external_provider and external_id")
            data["imported_at"] = data.get("imported_at") or datetime.now(timezone.utc).isoformat()
        data["external_provider"] = external_provider
        data["external_id"] = external_id or None
        data["external_order_id"] = external_order_id or None
        data["source_metadata"] = source_metadata

        ticker = str(data.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError("ticker/pair is required")
        data["ticker"] = ticker
        direction = str(data.get("direction") or "long").lower()
        if direction not in {"long", "short"}:
            raise ValueError("direction must be long or short")
        data["direction"] = direction
        data["fees"] = _number(data.get("fees")) or 0
        if data["fees"] < 0:
            raise ValueError("fees cannot be negative")

        # Manual day trades use the user's actual execution price. Position size can
        # be entered as money/notional; quantity is then derived for the maths. The
        # stored quantity is still retained because later broker imports/backtests
        # will naturally supply exact fills/quantities.
        point_value = 1.0
        futures = instrument_spec(ticker).asset_type == "future" and not source.startswith("broker_")
        if futures:
            contract = execution_contract(ticker,source_metadata)
            if source_metadata.get('executed_contract',contract) != contract:
                raise ValueError('Executed contract does not match source provenance')
            point_value, _, _ = execution_economics(contract)
            if str(data.get("position_currency") or "USD").upper() != "USD":
                raise ValueError("Futures accounting is USD only; currency conversion is not implemented")
            data["source_metadata"] = {**source_metadata, 'displayed_symbol':ticker,'executed_contract':contract, "contract_multiplier": point_value,
                "quantity_unit": "contracts", "economics_version": "cme-economics-v1"}
        entry = _number(data.get("entry_price"))
        position_amount = _number(data.get("position_amount"))
        quantity = _number(data.get("quantity"))
        if position_amount is not None:
            if position_amount <= 0:
                raise ValueError("position amount must be greater than zero")
            if entry is not None and entry > 0:
                data["quantity"] = position_amount / (entry * point_value)
                if futures:
                    data["quantity"] = math.floor(data["quantity"] + 1e-10)
        elif quantity is not None and quantity <= 0:
            raise ValueError("quantity must be greater than zero")
        if futures and (_number(data.get("quantity")) is None or float(data["quantity"]) <= 0 or not float(data["quantity"]).is_integer()):
            raise ValueError("Futures quantity must be a positive whole number of contracts")
        data["position_currency"] = str(data.get("position_currency") or "USD").upper()

        # Broker adapters own their accounting; generic price-difference maths
        # must never invent or replace broker account-currency P&L.
        if not source.startswith("broker_"):
            self._compute_metrics(data)

        closed = bool(data.get("closed_at") or data.get("exit_price") is not None)
        data["status"] = "closed" if closed else "open"
        if creating:
            data.setdefault("name", "Trade")
            data.setdefault("account", "Main")
        return data

    def _validate_review(self, data):
        review = data.get("review_data") or {}
        if not isinstance(review, dict):
            raise ValueError("Review data must be an object")
        for key in ("mistakes", "emotions", "confluences"):
            if key in review and (not isinstance(review[key], list) or any(not isinstance(v, str) for v in review[key])):
                raise ValueError(f"{key} must be a list of labels")
        custom = review.get("custom", {})
        if not isinstance(custom, dict) or any(not isinstance(v, (str, list, bool, int, float, type(None))) for v in custom.values()):
            raise ValueError("Custom review fields must contain simple values")
        if any(isinstance(v, list) and any(not isinstance(item, str) for item in v) for v in custom.values()):
            raise ValueError("Custom multi-choice answers must contain labels")
        for key in ("structure_alignment", "context_timeframe", "entry_relativity", "shift", "went_well", "went_wrong", "do_differently"):
            if key in review and not isinstance(review[key], str):
                raise ValueError(f"{key} must be text")
        labels = review.get("custom_labels", {})
        if not isinstance(labels, dict) or any(not isinstance(v, str) for v in labels.values()):
            raise ValueError("Custom labels must be text")
        if data.get("plan_followed") not in (None, "", "Yes", "No", "Partially"):
            raise ValueError("Plan followed must be Yes, No or Partially")
        if data.get("playbook_id"):
            with self.repository.database.connect() as connection:
                exists = connection.execute("SELECT id FROM playbook_entries WHERE id=?", (data["playbook_id"],)).fetchone()
            if not exists:
                raise ValueError("Playbook not found")

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
        point_value = execution_economics(execution_contract(data['ticker'],data.get('source_metadata') or {}))[0]
        gross_pnl = move_per_unit * point_value * quantity if quantity is not None else None
        calculated_pnl = gross_pnl - fees if gross_pnl is not None else None
        final_pnl = override if override is not None else calculated_pnl

        data["pnl_amount"] = final_pnl
        data["pnl_source"] = "manual_override" if override is not None else ("computed" if calculated_pnl is not None else None)

        if quantity is not None and entry * quantity != 0 and calculated_pnl is not None:
            data["pnl_pct"] = calculated_pnl / (entry * quantity * point_value) * 100
        else:
            data["pnl_pct"] = move_per_unit / entry * 100 if entry else None

        if stop is not None:
            risk_per_unit = abs(entry - stop)
            if risk_per_unit > 1e-12:
                if final_pnl is not None and quantity is not None and quantity > 0:
                    data["r_multiple"] = final_pnl / (risk_per_unit * quantity * point_value)
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
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Trade numbers must be finite")
    return number


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
