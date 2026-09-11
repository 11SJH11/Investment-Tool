from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.data.http import JsonHttpClient
from app.data.providers.base import FundamentalsProvider, SecurityMasterProvider, Symbol
from app.data.security_types import infer_security_type


_ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


@dataclass(frozen=True)
class FactPoint:
    value: float
    end: str
    filed: str
    form: str
    fiscal_year: int | None = None


class SecProvider(SecurityMasterProvider, FundamentalsProvider):
    key = "sec"

    def __init__(
        self,
        user_agent: str,
        *,
        data_base_url: str = "https://data.sec.gov",
        files_base_url: str = "https://www.sec.gov",
        http: JsonHttpClient | None = None,
    ):
        if not user_agent or "your-email@example.com" in user_agent:
            raise ValueError("SEC_USER_AGENT must identify your Ledger client and include a real contact email")
        self.user_agent = user_agent
        self.data_base_url = data_base_url.rstrip("/")
        self.files_base_url = files_base_url.rstrip("/")
        self.http = http or JsonHttpClient()
        self._directory: dict[str, dict[str, Any]] | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }

    def list_symbols(self) -> list[Symbol]:
        directory = self._load_directory()
        return [
            Symbol(
                ticker=ticker,
                name=str(item.get("name") or ticker),
                asset_type="equity",
                security_type=infer_security_type(str(item.get("name") or ticker), ticker),
                exchange=item.get("exchange"),
                status=None,
                cik=item.get("cik"),
            )
            for ticker, item in sorted(directory.items())
        ]

    def cik_map(self) -> dict[str, str]:
        return {ticker: str(item["cik"]) for ticker, item in self._load_directory().items() if item.get("cik")}

    def get_fundamentals(self, ticker: str) -> dict:
        symbol = ticker.strip().upper()
        directory = self._load_directory()
        company = directory.get(symbol)
        if not company:
            raise KeyError(f"SEC does not have a CIK mapping for {symbol}")

        cik = str(company["cik"]).zfill(10)
        payload = self.http.get_json(
            f"{self.data_base_url}/api/xbrl/companyfacts/CIK{cik}.json",
            headers=self.headers,
        )
        return self.normalize_company_facts(symbol, payload)

    def _load_directory(self) -> dict[str, dict[str, Any]]:
        if self._directory is not None:
            return self._directory
        payload = self.http.get_json(
            f"{self.files_base_url}/files/company_tickers_exchange.json",
            headers=self.headers,
        )
        self._directory = _parse_ticker_directory(payload)
        return self._directory

    def normalize_company_facts(self, ticker: str, payload: dict[str, Any]) -> dict:
        facts = payload.get("facts") or {}
        us_gaap = facts.get("us-gaap") or {}
        dei = facts.get("dei") or {}

        revenue = _latest_two(us_gaap, [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
        ], "USD", duration=True)
        net_income = _latest_two(us_gaap, ["NetIncomeLoss", "ProfitLoss"], "USD", duration=True)
        operating_income = _latest_two(us_gaap, ["OperatingIncomeLoss"], "USD", duration=True)
        assets = _latest_two(us_gaap, ["Assets"], "USD", duration=False)
        liabilities = _latest_two(us_gaap, ["Liabilities"], "USD", duration=False)
        equity = _latest_two(us_gaap, [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ], "USD", duration=False)
        cash = _latest_two(us_gaap, [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        ], "USD", duration=False)
        operating_cash_flow = _latest_two(us_gaap, ["NetCashProvidedByUsedInOperatingActivities"], "USD", duration=True)
        capex = _latest_two(us_gaap, [
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "PaymentsForAdditionsToPropertyPlantAndEquipment",
        ], "USD", duration=True)
        eps = _latest_two(us_gaap, ["EarningsPerShareDiluted"], "USD/shares", duration=True)
        shares = _latest_two(dei, ["EntityCommonStockSharesOutstanding"], "shares", duration=False)

        current_revenue = _value(revenue, 0)
        previous_revenue = _value(revenue, 1)
        current_net_income = _value(net_income, 0)
        current_operating_income = _value(operating_income, 0)
        current_ocf = _value(operating_cash_flow, 0)
        current_capex = _value(capex, 0)
        current_equity = _value(equity, 0)

        free_cash_flow = None
        if current_ocf is not None and current_capex is not None:
            free_cash_flow = current_ocf - abs(current_capex)

        period = revenue[0] if revenue else (assets[0] if assets else None)
        return {
            "ticker": ticker,
            "cik": str(payload.get("cik") or "").zfill(10),
            "company_name": payload.get("entityName") or ticker,
            "source": "sec",
            "fiscal_year": period.fiscal_year if period else None,
            "period_end": period.end if period else None,
            "revenue": current_revenue,
            "revenue_growth_yoy": _growth(current_revenue, previous_revenue),
            "net_income": current_net_income,
            "net_margin": _ratio(current_net_income, current_revenue),
            "operating_income": current_operating_income,
            "operating_margin": _ratio(current_operating_income, current_revenue),
            "assets": _value(assets, 0),
            "liabilities": _value(liabilities, 0),
            "equity": current_equity,
            "cash": _value(cash, 0),
            "operating_cash_flow": current_ocf,
            "capital_expenditure": current_capex,
            "free_cash_flow": free_cash_flow,
            "eps_diluted": _value(eps, 0),
            "shares_outstanding": _value(shares, 0),
            "return_on_equity": _ratio(current_net_income, current_equity),
        }


def _parse_ticker_directory(payload: Any) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict) and "fields" in payload and "data" in payload:
        fields = list(payload["fields"])
        for row in payload["data"]:
            item = dict(zip(fields, row))
            ticker = str(item.get("ticker") or "").strip().upper()
            if ticker:
                result[ticker] = {
                    "cik": str(item.get("cik") or "").zfill(10),
                    "name": item.get("name") or ticker,
                    "exchange": item.get("exchange"),
                }
        return result

    # company_tickers.json has historically used an object keyed by numeric strings.
    if isinstance(payload, dict):
        for item in payload.values():
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            if ticker:
                result[ticker] = {
                    "cik": str(item.get("cik_str") or item.get("cik") or "").zfill(10),
                    "name": item.get("title") or item.get("name") or ticker,
                    "exchange": item.get("exchange"),
                }
    return result


def _latest_two(
    taxonomy: dict[str, Any],
    tags: Iterable[str],
    unit: str,
    *,
    duration: bool,
) -> list[FactPoint]:
    points: list[FactPoint] = []
    for tag in tags:
        fact = taxonomy.get(tag) or {}
        units = fact.get("units") or {}
        entries = units.get(unit) or []
        candidates: list[dict[str, Any]] = []
        for entry in entries:
            if entry.get("form") not in _ANNUAL_FORMS or not entry.get("end") or entry.get("val") is None:
                continue
            if entry.get("fp") not in (None, "FY"):
                continue
            if duration:
                if not entry.get("start"):
                    continue
                days = _duration_days(entry.get("start"), entry.get("end"))
                if days is not None and days < 270:
                    continue
            candidates.append(entry)
        if candidates:
            # Prefer the first available standard tag, not a mixture of tag definitions.
            points = _dedupe_periods(candidates)
            break
    return points[:2]


def _dedupe_periods(entries: list[dict[str, Any]]) -> list[FactPoint]:
    by_end: dict[str, dict[str, Any]] = {}
    for entry in entries:
        end = str(entry["end"])
        current = by_end.get(end)
        if current is None or str(entry.get("filed") or "") > str(current.get("filed") or ""):
            by_end[end] = entry
    ordered = sorted(by_end.values(), key=lambda item: (str(item.get("end") or ""), str(item.get("filed") or "")), reverse=True)
    return [
        FactPoint(
            value=float(item["val"]),
            end=str(item["end"]),
            filed=str(item.get("filed") or ""),
            form=str(item.get("form") or ""),
            fiscal_year=int(item["fy"]) if item.get("fy") is not None else None,
        )
        for item in ordered
    ]


def _duration_days(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    from datetime import date

    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError:
        return None


def _value(points: list[FactPoint], index: int) -> float | None:
    return points[index].value if len(points) > index else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)
