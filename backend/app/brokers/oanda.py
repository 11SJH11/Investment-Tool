"""OANDA v20 history adapter. The transport exposes GET only; never execution.

Reference: developer.oanda.com/rest-live-v20/{trade,transaction,account}-ep/
Provider decimal strings are retained in metadata and calculated with Decimal.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import time

import httpx

from app.brokers.base import BrokerHistoryError, HistoryBatch


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise BrokerHistoryError("OANDA returned incomplete or invalid numeric history") from None


def utc_time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise BrokerHistoryError("OANDA returned an invalid or ambiguous timestamp") from None


def history_list(payload, key):
    items = payload.get(key)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise BrokerHistoryError("OANDA returned incomplete history; sync cursor was not advanced")
    return items


class OandaHistory:
    provider = "oanda"

    def __init__(self, token, account_id, environment="practice", *, client=None):
        if not token or not account_id:
            raise BrokerHistoryError("OANDA Journal Sync is not configured")
        if environment not in {"practice", "live"}:
            raise BrokerHistoryError("OANDA environment must be practice or live")
        self.environment = environment
        self.account_key = sha256(f"oanda:{environment}:{account_id}".encode()).hexdigest()
        self.account_label = f"OANDA {environment} · {self.account_key[:8]}"
        self._account_id = account_id
        self._token = token
        self._base = "https://api-fxpractice.oanda.com" if environment == "practice" else "https://api-fxtrade.oanda.com"
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)

    def close(self):
        self._client.close()

    def capability_report(self):
        return {"provider": self.provider, "destination": "journal", "read_only": True,
                "closed_trades": True, "execution": False, "supported": True}

    def accounts(self):
        return [{"account_key": self.account_key, "label": self.account_label, "environment": self.environment}]

    def _get(self, suffix, params=None):
        # Construct paths locally: never forward authentication to a pagination URL.
        try:
            for attempt in range(3):
                response = self._client.get(
                    f"{self._base}/v3/accounts/{self._account_id}/{suffix}", params=params,
                    headers={"Authorization": f"Bearer {self._token}", "Accept-Datetime-Format": "RFC3339"},
                )
                if response.status_code == 429:
                    from app.data.http import _retry_delay
                    raise BrokerHistoryError('OANDA history is rate-limited; last good data retained', status_code=429, retry_after=max(60, _retry_delay(response, attempt+1)))
                if response.status_code >= 500:
                    if attempt < 2:
                        time.sleep(0.25 * (attempt + 1))
                        continue
                if response.status_code != 200:
                    raise BrokerHistoryError(f"OANDA history request failed (HTTP {response.status_code})")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise BrokerHistoryError("OANDA returned invalid history")
                return payload
        except BrokerHistoryError:
            raise
        except Exception:
            # Do not echo URLs, headers, provider bodies or transport exception text.
            raise BrokerHistoryError("OANDA history could not be read; check configuration and retry") from None

    def fetch_closed(self, cursor):
        account = self._get("summary")["account"]
        high = int(account["lastTransactionID"])
        currency = str(account["currency"])
        if cursor and int(cursor) > high:
            raise BrokerHistoryError("OANDA history cursor is ahead of this account; sync was not changed")
        transactions = {}
        # Capture a high-water mark before fetching. Never commit a newer cursor
        # merely because a later response observed additional transactions.
        for start in range(int(cursor or 0) + 1, high + 1, 1000):
            payload = self._get("transactions/idrange", {"from": str(start), "to": str(min(high, start + 999))})
            for tx in history_list(payload, "transactions"):
                if int(tx["id"]) <= high:
                    transactions[str(tx["id"])] = tx
        trades = []
        if cursor:
            affected = set()
            for tx in transactions.values():
                affected.update(str(t["tradeID"]) for t in tx.get("tradesClosed", []))
                if tx.get("tradeReduced"):
                    affected.add(str(tx["tradeReduced"]["tradeID"]))
            for trade_id in sorted(affected, key=int):
                trades.append(self._get(f"trades/{trade_id}")["trade"])
        else:
            before = None
            while True:
                params = {"state": "CLOSED", "count": 500}
                if before:
                    params["beforeID"] = before
                page = history_list(self._get("trades", params), "trades")
                if not page:
                    break
                trades.extend(page)
                next_before = str(min(int(t["id"]) for t in page) - 1)
                if before and int(next_before) >= int(before):
                    raise BrokerHistoryError("OANDA trade pagination did not advance")
                before = next_before
                if len(page) < 500 or int(before) <= 0:
                    break

        def transaction(tx_id):
            key = str(tx_id)
            if key not in transactions:
                transactions[key] = self._get(f"transactions/{int(key)}")["transaction"]
            return transactions[key]

        mapped = []
        seen = set()
        for trade in trades:
            trade_id = str(trade["id"])
            if trade_id in seen or trade.get("state") != "CLOSED":
                continue
            seen.add(trade_id)
            close_ids = trade.get("closingTransactionIDs") or []
            if not close_ids:
                raise BrokerHistoryError("OANDA closed trade is missing closing transaction IDs")
            if any(int(i) > high for i in close_ids):
                # A trade closed during pagination belongs to the next sync.
                continue
            opening = transaction(trade_id)
            closing = [transaction(i) for i in close_ids]
            # Dependent protection created in the opening batch is historical
            # evidence; current stopLossOrder/takeProfitOrder are not initial orders.
            batch_id = str(opening.get("batchID") or opening["id"])
            if cursor:
                batch = self._get("transactions/idrange", {"from": batch_id, "to": str(min(high, int(trade_id) + 20))})
                for tx in history_list(batch, "transactions"):
                    transactions[str(tx["id"])] = tx
            protection = [t for t in transactions.values() if str(t.get("batchID")) == batch_id and str(t.get("tradeID")) == trade_id and t.get("reason") == "ON_FILL"]
            mapped.append(self._map(trade, opening, closing, protection, currency))
        return HistoryBatch(mapped, str(high))

    def _map(self, trade, opening, closing, protection, currency):
        trade_id = str(trade["id"])
        opened = opening.get("tradeOpened") or {}
        if str(opened.get("tradeID")) != trade_id:
            raise BrokerHistoryError("OANDA opening fill does not match the closed trade")
        units = abs(number(trade["initialUnits"]))
        if not units or number(trade["currentUnits"]) != 0:
            raise BrokerHistoryError("OANDA closed trade has inconsistent units")
        if number(opened.get("units")) != number(trade["initialUnits"]):
            raise BrokerHistoryError("OANDA opening units do not reconcile")
        start, end = utc_time(trade["openTime"]), utc_time(trade["closeTime"])
        if end < start or any(not start <= utc_time(tx["time"]) <= end for tx in closing):
            raise BrokerHistoryError("OANDA fill timestamps do not reconcile")
        entry = number(opened.get("price", trade["price"]))
        fills = []
        for tx in closing:
            reductions = list(tx.get("tradesClosed", [])) + ([tx["tradeReduced"]] if tx.get("tradeReduced") else [])
            matched = [x for x in reductions if str(x.get("tradeID")) == trade_id]
            if len(matched) != 1:
                raise BrokerHistoryError("OANDA reduction history is incomplete")
            fills.append({**{k: matched[0][k] for k in ("tradeID", "units", "price", "realizedPL", "financing", "guaranteedExecutionFee", "halfSpreadCost") if k in matched[0]}, "transaction_id": str(tx["id"]), "order_id": str(tx.get("orderID") or ""), "time": tx["time"]})
        total = sum((abs(number(f["units"])) for f in fills), Decimal(0))
        if total != units:
            raise BrokerHistoryError("OANDA partial-close units do not reconcile")
        exit_price = sum((abs(number(f["units"])) * number(f["price"]) for f in fills), Decimal(0)) / units
        realized = number(trade["realizedPL"])
        if abs(sum((number(f["realizedPL"]) for f in fills), Decimal(0)) - realized) > Decimal("0.00001"):
            raise BrokerHistoryError("OANDA partial-close P&L does not reconcile")
        financing = number(trade["financing"]) if trade.get("financing") is not None else None
        dividend = number(trade.get("dividendAdjustment", "0"))
        # Order-wide commission is attributable only when that fill affects one
        # logical trade. Never allocate an entire multi-trade fee to each trade.
        commission = Decimal(0)
        complete = financing is not None
        for tx in {str(t["id"]): t for t in [opening, *closing]}.values():
            if tx.get("commission") is None:
                complete = False
            affected = len(tx.get("tradesClosed", [])) + bool(tx.get("tradeReduced")) + bool(tx.get("tradeOpened"))
            fee = number(tx.get("commission", "0"))
            if affected != 1 and fee:
                complete = False
            else:
                commission += fee
        guaranteed = sum((number(f.get("guaranteedExecutionFee", "0")) for f in [opened, *fills]), Decimal(0))
        for tx in [opening, *closing]:
            parts = [*tx.get("tradesClosed", []), *([tx["tradeReduced"]] if tx.get("tradeReduced") else []), *([tx["tradeOpened"]] if tx.get("tradeOpened") else [])]
            if number(tx.get("guaranteedExecutionFee", "0")) != sum((number(p.get("guaranteedExecutionFee", "0")) for p in parts), Decimal(0)):
                complete = False
        net = realized + (financing or 0) + dividend - commission - guaranteed if complete else None
        def initial(kind):
            values = {str(t["price"]) for t in protection if t.get("type") in kind and t.get("price") is not None}
            return number(next(iter(values))) if len(values) == 1 else None
        stop = initial({"STOP_LOSS_ORDER", "GUARANTEED_STOP_LOSS_ORDER"})
        target = initial({"TAKE_PROFIT_ORDER"})
        long = number(trade["initialUnits"]) > 0
        valid_stop = stop is not None and ((stop < entry) if long else (stop > entry))
        # Initial risk in home currency: use historical loss conversion factors.
        quote = trade["instrument"].split("_")[-1]
        factor = Decimal(1) if quote == currency else None
        conversion = (opening.get("homeConversionFactors") or {}).get("lossQuoteHome")
        if conversion and conversion.get("factor") is not None:
            factor = number(conversion["factor"])
        elif opening.get("lossQuoteHomeConversionFactor") is not None:
            factor = number(opening["lossQuoteHomeConversionFactor"])
        risk = abs(entry - stop) * units * factor if valid_stop and factor is not None and factor > 0 else None
        rr = abs(target - entry) / abs(entry - stop) if valid_stop and target is not None and ((target > entry) if long else (target < entry)) else None
        basis = net if net is not None else realized
        metadata = {
            "trade_id": trade_id, "environment": self.environment,
            "open_time": trade["openTime"], "close_time": trade["closeTime"],
            "closing_transaction_ids": [str(t["id"]) for t in closing],
            "opening_transaction_id": str(opening["id"]), "fills": fills,
            "opening_fill": {k: opened.get(k) for k in ("tradeID", "units", "price", "halfSpreadCost", "guaranteedExecutionFee")},
            "initial_protection": [{k: t.get(k) for k in ("id", "tradeID", "type", "reason", "price", "time")} for t in protection], "home_conversion_factors": opening.get("homeConversionFactors"),
            "reported_average_close_price": trade.get("averageClosePrice"),
            "costs_complete": complete, "pnl_basis": "net" if complete else "realized_excluding_unallocated_costs",
            "cost_note": None if complete else "Net P&L unavailable: one or more costs cannot be attributed reliably",
            "order_costs": [{k: t.get(k) for k in ("id", "orderID", "commission", "financing", "guaranteedExecutionFee", "halfSpreadCost")} for t in [opening, *closing]],
        }
        return {
            "source": "broker_oanda", "name": "OANDA closed trade", "account": self.account_label,
            "external_provider": "oanda", "external_account_key": self.account_key,
            "external_id": f"{self.environment}:{self.account_key}:{trade_id}", "external_order_id": str(opening.get("orderID") or ""),
            "ticker": "XAUUSD" if trade["instrument"] == "XAU_USD" else trade["instrument"],
            "direction": "long" if long else "short", "status": "closed",
            "opened_at": start.isoformat(), "closed_at": end.isoformat(),
            "entry_price": float(entry), "exit_price": float(exit_price), "quantity": float(units),
            "position_currency": currency, "account_currency": currency, "position_amount": None,
            "stop_loss": float(stop) if stop is not None else None, "take_profit": float(target) if target is not None else None,
            "broker_realized_pnl": float(realized), "pnl_amount": float(net) if net is not None else None, "pnl_source": "broker_reported",
            "result": ("win" if basis > 0 else "loss" if basis < 0 else "breakeven") if net is not None else None, "result_source": "computed" if net is not None else None,
            "financing": float(financing) if financing is not None else None, "commission": float(commission) if complete else None,
            "guaranteed_execution_fee": float(guaranteed), "dividend_adjustment": float(dividend), "fees": float(commission + guaranteed) if complete else 0,
            "costs_complete": complete, "pnl_pct": None, "pnl_override": None,
            "initial_risk_amount": float(risk) if risk else None, "risk_source": "historical_initial_stop_home_currency" if risk else None,
            "r_multiple": float(net / risk) if risk and net is not None else None, "planned_rr": float(rr) if rr is not None else None,
            "source_metadata": metadata, "imported_at": datetime.now(timezone.utc).isoformat(),
        }
