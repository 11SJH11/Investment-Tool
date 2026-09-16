"""Official Trading 212 v0 GET-only Portfolio adapter; no execution interface.

Schemas: https://docs.trading212.com/api/{accounts,positions,historical-events}
History is evidence, never synthesized into buys used to reconstruct holdings.
"""
from dataclasses import dataclass
from hashlib import sha256
import math
import time
from urllib.parse import urlsplit

import httpx

from app.brokers.base import BrokerHistoryError


def select(data, names):
    if not isinstance(data, dict):
        raise BrokerHistoryError("Trading 212 returned an invalid record; previous data preserved")
    return {k: data[k] for k in names.split() if k in data}


def numeric(data, names):
    result = select(data, names)
    if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in result.values()):
        raise BrokerHistoryError("Trading 212 returned invalid numeric facts")
    return result


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise BrokerHistoryError("Trading 212 history lacks a stable provider identity")
    return str(value)


def instrument(data):
    return select(data, "ticker isin name currency")


@dataclass
class PortfolioSnapshot:
    summary: dict
    positions: list[dict]
    events: list[dict]


class Trading212Portfolio:
    provider = "trading212"

    def __init__(self, api_key, api_secret, environment, *, client=None, sleep=time.sleep):
        if not api_key.strip() or not api_secret.strip() or environment not in {"demo", "live"}:
            raise BrokerHistoryError("Trading 212 is not configured")
        self.environment = environment
        self._base = f"https://{environment}.trading212.com"
        self._auth = httpx.BasicAuth(api_key.strip(), api_secret.strip())
        self._client = client or httpx.Client(timeout=30, follow_redirects=False)
        self._sleep = sleep
        self._ready = {}
        self._deadline = time.monotonic() + 180
        self.account_key = self.account_label = None

    @staticmethod
    def capability_report():
        return {"provider": "trading212", "destination": "portfolio", "supported": True,
                "read_only": True, "execution": False, "positions": True, "history": True,
                "reason": "Invest/Stocks ISA only; holdings use broker snapshots, history is not a reconstructed equity curve"}

    def close(self):
        self._client.close()

    def _wait(self, seconds):
        seconds = max(0, seconds)
        if seconds > 60 or time.monotonic() + seconds >= self._deadline:
            raise BrokerHistoryError("Trading 212 sync exceeded its rate-limit/time budget; previous data preserved. Retry later.")
        if seconds:
            self._sleep(seconds)

    def _get(self, path, expected):
        # Never send auth to an arbitrary nextPagePath host or different endpoint.
        parts = urlsplit(path)
        if parts.scheme or parts.netloc or parts.fragment or parts.path != expected or "\\" in path:
            raise BrokerHistoryError("Trading 212 returned unsafe pagination")
        try:
            for attempt in range(3):
                self._wait(self._ready.get(expected, 0) - time.time())
                if time.monotonic() >= self._deadline:
                    raise BrokerHistoryError("Trading 212 sync timed out; previous data preserved")
                response = self._client.get(self._base + path, auth=self._auth, follow_redirects=False)
                if response.headers.get("x-ratelimit-remaining") == "0":
                    self._ready[expected] = float(response.headers.get("x-ratelimit-reset", time.time()+10)) + .1
                if response.status_code == 429 and attempt < 2:
                    self._wait(float(response.headers.get("Retry-After", "10")))
                    continue
                if response.status_code != 200:
                    raise BrokerHistoryError(f"Trading 212 read failed (HTTP {response.status_code}); previous data preserved")
                return response.json()
        except BrokerHistoryError:
            raise
        except Exception:
            raise BrokerHistoryError("Trading 212 data could not be read; check read permissions and retry") from None

    def read_account(self):
        path = "/api/v0/equity/account/summary"
        raw = self._get(path, path)
        account_id = identifier(raw.get("id"))
        self.account_key = sha256(f"trading212:{self.environment}:{account_id}".encode()).hexdigest()
        self.account_label = f"Trading 212 {self.environment} / {self.account_key[:8]}"
        result = {**select(raw, "currency"), **numeric(raw, "totalValue"),
                  "cash": numeric(raw.get("cash", {}), "availableToTrade inPies reservedForOrders"),
                  "investments": numeric(raw.get("investments", {}), "currentValue realizedProfitLoss totalCost unrealizedProfitLoss")}
        if not isinstance(result.get("currency"), str) or not result["currency"]:
            raise BrokerHistoryError("Trading 212 account currency is unavailable")
        return result

    def accounts(self):
        return [] if not self.account_key else [{"account_key": self.account_key, "label": self.account_label, "environment": self.environment}]

    def _history(self, kind):
        endpoint = f"/api/v0/equity/history/{kind}"
        path = endpoint + "?limit=50"
        visited = set()
        for _ in range(200):
            if path in visited:
                raise BrokerHistoryError("Trading 212 pagination did not advance")
            visited.add(path)
            page = self._get(path, endpoint)
            if not isinstance(page, dict) or not isinstance(page.get("items"), list) or "nextPagePath" not in page:
                raise BrokerHistoryError("Trading 212 returned incomplete history")
            for row in page["items"]:
                yield self.normalize_event(kind, row)
            path = page["nextPagePath"]
            if path is None:
                return
            if not isinstance(path, str) or not path:
                raise BrokerHistoryError("Trading 212 pagination is invalid")
        raise BrokerHistoryError("Trading 212 history exceeds the 200-page sync limit; previous data preserved")

    @staticmethod
    def normalize_event(kind, raw):
        if kind == "orders":
            order = raw.get("order", {})
            order_id = identifier(order.get("id"))
            fill = raw.get("fill")
            # One order can have several fills; retaining only order ID loses fills.
            external_id = order_id + ":" + (identifier(fill.get("id")) if fill else "order")
            facts = {"order": {**select(order, "id createdAt currency side status ticker type strategy timeInForce initiatedFrom extendedHours"),
                      **numeric(order, "quantity filledQuantity filledValue value limitPrice stopPrice"),
                      "instrument": instrument(order.get("instrument", {}))}, "fill": None}
            if fill:
                wallet = fill.get("walletImpact") or {}
                facts["fill"] = {**select(fill, "id filledAt type tradingMethod"), **numeric(fill, "price quantity"),
                    "walletImpact": {**select(wallet, "currency"), **numeric(wallet, "fxRate netValue realisedProfitLoss"),
                        "taxes": [{**select(t, "name currency chargedAt"), **numeric(t, "quantity")} for t in wallet.get("taxes", [])]}}
        else:
            external_id = identifier(raw.get("reference"))
            facts = {**select(raw, "reference currency dateTime paidOn type ticker tickerCurrency"),
                     **numeric(raw, "amount amountInEuro grossAmountPerShare quantity")}
            if kind == "dividends":
                facts["instrument"] = instrument(raw.get("instrument", {}))
        return {"kind": kind, "external_id": external_id, "facts": facts}

    def fetch_snapshot(self, summary):
        path = "/api/v0/equity/positions"
        raw = self._get(path, path)
        if not isinstance(raw, list):
            raise BrokerHistoryError("Trading 212 returned incomplete positions")
        positions = []
        for row in raw:
            if numeric(row, 'quantity').get('quantity') is None:
                raise BrokerHistoryError("Trading 212 returned a position without quantity")
            inst = instrument(row.get("instrument", {}))
            positions.append({"kind": "position", "external_id": identifier(inst.get("ticker")), "facts": {
                "instrument": inst, **select(row, "createdAt"),
                **numeric(row, "quantity quantityAvailableForTrading quantityInPies averagePricePaid currentPrice"),
                "walletImpact": {**select(row.get("walletImpact", {}), "currency"),
                                 **numeric(row.get("walletImpact", {}), "currentValue fxImpact totalCost unrealizedProfitLoss")}}})
        if len({p["external_id"] for p in positions}) != len(positions):
            raise BrokerHistoryError("Trading 212 returned duplicate positions")
        events = [row for kind in ("orders", "dividends", "transactions") for row in self._history(kind)]
        return PortfolioSnapshot(summary, positions, events)
