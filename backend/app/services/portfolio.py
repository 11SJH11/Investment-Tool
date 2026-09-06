from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.execution_price import ExecutionPriceService
from app.services.fx import FxRateService
from app.services.screener import ScreenerService
from app.storage.portfolio_repository import PortfolioRepository
from app.storage.screener_repository import ScreenerRepository


@dataclass
class _PositionState:
    quantity: float = 0.0
    cost_basis_native: float = 0.0
    cost_basis_base: float = 0.0
    realized_pnl_native: float = 0.0
    realized_pnl_base: float = 0.0
    has_base_cost: bool = True

    @property
    def average_cost(self) -> float | None:
        return self.cost_basis_native / self.quantity if self.quantity > 1e-12 else None


class PortfolioService:
    def __init__(
        self,
        repository: PortfolioRepository,
        screener_repository: ScreenerRepository,
        screener: ScreenerService,
        execution_prices: ExecutionPriceService | None = None,
        fx: FxRateService | None = None,
    ):
        self.repository = repository
        self.screener_repository = screener_repository
        self.screener = screener
        self.execution_prices = execution_prices or ExecutionPriceService(None)
        self.fx = fx or FxRateService(None)

    def add_transaction(self, payload: dict) -> dict:
        action = str(payload.get("action") or "").upper()
        if action not in {"BUY", "SELL"}:
            raise ValueError("action must be BUY or SELL")
        ticker = str(payload.get("ticker") or "").strip().upper()
        if not ticker:
            raise ValueError("ticker is required")
        occurred_at = _parse_datetime(payload.get("occurred_at"))
        fees = float(payload.get("fees") or 0)
        if fees < 0:
            raise ValueError("fees cannot be negative")

        input_mode = str(payload.get("input_mode") or "quantity").lower()
        if input_mode not in {"amount", "quantity"}:
            raise ValueError("input_mode must be amount or quantity")

        base_currency = str(payload.get("base_currency") or "GBP").upper()
        asset_currency = str(payload.get("asset_currency") or "USD").upper()
        price_override = payload.get("price_override")
        # Backward-compatible Phase 4 clients/tests may still send price directly.
        if price_override is None and payload.get("price") is not None:
            price_override = payload.get("price")
        resolved_price = self.execution_prices.resolve(ticker, occurred_at, price_override)
        price = float(resolved_price["price"])

        input_amount = None
        fx_rate = None
        fx_source = None
        fees_currency = str(payload.get("fees_currency") or base_currency).upper()

        if input_mode == "amount":
            input_amount = float(payload.get("amount") or payload.get("input_amount") or 0)
            if input_amount <= 0:
                raise ValueError("transaction amount must be greater than zero")
            fx_info = self.fx.rate(base_currency, asset_currency, occurred_at)
            fx_rate = float(fx_info["rate"])
            fx_source = fx_info.get("source")
            asset_amount = input_amount * fx_rate
            quantity = asset_amount / price
        else:
            quantity = float(payload.get("quantity") or 0)
            if quantity <= 0:
                raise ValueError("quantity must be greater than zero")
            # Store historical FX for quantity-entered transactions when available,
            # but don't make manual broker-fill entry unusable if FRED is unavailable.
            try:
                fx_info = self.fx.rate(base_currency, asset_currency, occurred_at)
                fx_rate = float(fx_info["rate"])
                fx_source = fx_info.get("source")
            except Exception:
                fx_rate = None

        candidate = {
            **payload,
            "ticker": ticker,
            "action": action,
            "occurred_at": occurred_at.isoformat(),
            "quantity": quantity,
            "price": price,
            "fees": fees,
            "input_mode": input_mode,
            "input_amount": input_amount,
            "base_currency": base_currency,
            "asset_currency": asset_currency,
            "fx_rate": fx_rate,
            "fx_source": fx_source,
            "price_source": resolved_price.get("source"),
            "price_timestamp": resolved_price.get("timestamp"),
            "price_overridden": bool(resolved_price.get("overridden")),
            "fees_currency": fees_currency,
        }
        txs = self.repository.list_transactions(payload.get("account") or "Main") + [
            {**candidate, "id": 10**15}
        ]
        self._compute_states(sorted(txs, key=lambda item: (item["occurred_at"], item.get("id", 0))))
        return self.repository.add_transaction(candidate)

    def delete_transaction(self, transaction_id: int) -> bool:
        target = self.repository.get_transaction(transaction_id)
        if target is None:
            return False
        remaining = [tx for tx in self.repository.list_transactions(target["account"]) if tx["id"] != transaction_id]
        self._compute_states(remaining)
        return self.repository.delete_transaction(transaction_id)

    def summary(self, account: str | None = None, *, refresh_prices: bool = False) -> dict:
        transactions = self.repository.list_transactions(account)
        states = self._compute_states(transactions)
        tickers = [ticker for ticker, state in states.items() if state.quantity > 1e-12]
        holdings: list[dict] = []
        total_value_native = 0.0
        total_value_base = 0.0
        total_cost_native = 0.0
        total_cost_base = 0.0
        total_realized_native = sum(state.realized_pnl_native for state in states.values())
        total_realized_base = sum(state.realized_pnl_base for state in states.values())

        base_currency = _portfolio_base_currency(transactions)
        asset_currency = "USD"
        current_fx = None
        try:
            current_fx = self.fx.latest(base_currency, asset_currency)
        except Exception:
            current_fx = None
        usd_per_base = float(current_fx["rate"]) if current_fx else None

        for ticker in tickers:
            state = states[ticker]
            metrics = self.screener_repository.get_metrics(ticker) or {}
            if refresh_prices or metrics.get("price") is None:
                try:
                    self.screener.refresh_one_price(ticker)
                    metrics = self.screener_repository.get_metrics(ticker) or metrics
                except Exception:
                    pass
            price = metrics.get("price")
            value_native = float(price) * state.quantity if price is not None else None
            unrealized_native = value_native - state.cost_basis_native if value_native is not None else None
            value_base = (value_native / usd_per_base) if value_native is not None and usd_per_base else None
            unrealized_base = (
                value_base - state.cost_basis_base
                if value_base is not None and state.has_base_cost
                else None
            )
            total_cost_native += state.cost_basis_native
            if state.has_base_cost:
                total_cost_base += state.cost_basis_base
            if value_native is not None:
                total_value_native += value_native
            if value_base is not None:
                total_value_base += value_base
            holdings.append(
                {
                    "ticker": ticker,
                    "quantity": round(state.quantity, 8),
                    "average_cost": state.average_cost,
                    "cost_basis": state.cost_basis_native,
                    "current_price": price,
                    "market_value": value_native,
                    "unrealized_pnl": unrealized_native,
                    "unrealized_return_pct": (unrealized_native / state.cost_basis_native * 100) if unrealized_native is not None and state.cost_basis_native else None,
                    "realized_pnl": state.realized_pnl_native,
                    "base_cost_basis": state.cost_basis_base if state.has_base_cost else None,
                    "base_market_value": value_base,
                    "base_unrealized_pnl": unrealized_base,
                    "base_unrealized_return_pct": (unrealized_base / state.cost_basis_base * 100) if unrealized_base is not None and state.cost_basis_base else None,
                    "base_realized_pnl": state.realized_pnl_base if state.has_base_cost else None,
                    "price_timestamp": metrics.get("price_timestamp"),
                }
            )

        allocation_total = total_value_base if total_value_base > 0 else total_value_native
        for holding in holdings:
            alloc_value = holding.get("base_market_value") if total_value_base > 0 else holding.get("market_value")
            holding["allocation_pct"] = alloc_value / allocation_total * 100 if allocation_total > 0 and alloc_value is not None else None
        holdings.sort(key=lambda item: item.get("base_market_value") or item.get("market_value") or 0, reverse=True)
        unrealized_native_total = total_value_native - total_cost_native if holdings else 0.0
        base_complete = bool(transactions) and all(state.has_base_cost for state in states.values()) and usd_per_base is not None
        unrealized_base_total = total_value_base - total_cost_base if holdings and base_complete else None
        return {
            "account": account or "All",
            "base_currency": base_currency,
            "asset_currency": asset_currency,
            "fx_rate": usd_per_base,
            "fx_source": current_fx.get("source") if current_fx else None,
            "fx_date": current_fx.get("date") if current_fx else None,
            "base_currency_complete": base_complete,
            # Native/USD fields retained for compatibility and transparency.
            "market_value": total_value_native,
            "open_cost_basis": total_cost_native,
            "unrealized_pnl": unrealized_native_total,
            "unrealized_return_pct": (unrealized_native_total / total_cost_native * 100) if total_cost_native else None,
            "realized_pnl": total_realized_native,
            "total_pnl": total_realized_native + unrealized_native_total,
            # Preferred portfolio-level base-currency fields.
            "base_market_value": total_value_base if usd_per_base else None,
            "base_open_cost_basis": total_cost_base if base_complete else None,
            "base_unrealized_pnl": unrealized_base_total,
            "base_unrealized_return_pct": (unrealized_base_total / total_cost_base * 100) if unrealized_base_total is not None and total_cost_base else None,
            "base_realized_pnl": total_realized_base if base_complete else None,
            "base_total_pnl": (total_realized_base + unrealized_base_total) if unrealized_base_total is not None and base_complete else None,
            "position_count": len(holdings),
            "largest_position_pct": max((h.get("allocation_pct") or 0 for h in holdings), default=0),
            "holdings": holdings,
            "transactions": list(reversed(transactions)),
            "accounts": self.repository.accounts(),
        }

    def _compute_states(self, transactions: list[dict]) -> dict[str, _PositionState]:
        states: dict[str, _PositionState] = {}
        for tx in sorted(transactions, key=lambda item: (item["occurred_at"], item.get("id", 0))):
            ticker = str(tx["ticker"]).upper()
            state = states.setdefault(ticker, _PositionState())
            qty = float(tx["quantity"])
            price = float(tx["price"])
            fees = float(tx.get("fees") or 0)
            fx_rate = float(tx["fx_rate"]) if tx.get("fx_rate") not in (None, "") else None
            fees_currency = str(tx.get("fees_currency") or tx.get("asset_currency") or "USD").upper()
            base_currency = str(tx.get("base_currency") or "GBP").upper()
            asset_currency = str(tx.get("asset_currency") or "USD").upper()
            fee_native = fees if fees_currency == asset_currency else (fees * fx_rate if fx_rate else 0.0)
            fee_base = fees if fees_currency == base_currency else (fees / fx_rate if fx_rate else 0.0)

            if str(tx["action"]).upper() == "BUY":
                state.quantity += qty
                native_cost = qty * price + fee_native
                state.cost_basis_native += native_cost
                if tx.get("input_mode") == "amount" and tx.get("input_amount") is not None:
                    state.cost_basis_base += float(tx["input_amount"]) + fee_base
                elif fx_rate:
                    state.cost_basis_base += native_cost / fx_rate
                else:
                    state.has_base_cost = False
            else:
                if qty > state.quantity + 1e-9:
                    raise ValueError(f"Cannot sell {qty:g} {ticker}; only {state.quantity:g} held at that point")
                avg_native = state.average_cost or 0.0
                removed_native = avg_native * qty
                avg_base = state.cost_basis_base / state.quantity if state.quantity > 1e-12 and state.has_base_cost else 0.0
                removed_base = avg_base * qty
                proceeds_native = qty * price - fee_native
                state.realized_pnl_native += proceeds_native - removed_native
                if fx_rate and state.has_base_cost:
                    proceeds_base = (qty * price) / fx_rate - fee_base
                    state.realized_pnl_base += proceeds_base - removed_base
                else:
                    state.has_base_cost = False
                state.quantity -= qty
                state.cost_basis_native -= removed_native
                if state.has_base_cost:
                    state.cost_basis_base -= removed_base
                if state.quantity <= 1e-9:
                    state.quantity = 0.0
                    state.cost_basis_native = 0.0
                    state.cost_basis_base = 0.0
        return states


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif value:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _portfolio_base_currency(transactions: list[dict]) -> str:
    for tx in transactions:
        if tx.get("base_currency"):
            return str(tx["base_currency"]).upper()
    return "GBP"
