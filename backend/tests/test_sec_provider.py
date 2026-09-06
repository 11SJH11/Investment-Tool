import pytest

from app.data.providers.sec import SecProvider
from tests.fakes import FakeJsonHttpClient


DIRECTORY = {
    "fields": ["cik", "name", "ticker", "exchange"],
    "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]],
}


def _fact(label, unit, entries):
    return {"label": label, "units": {unit: entries}}


COMPANY_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": _fact("Revenue", "USD", [
                {"start": "2023-10-01", "end": "2024-09-28", "val": 390000000000, "form": "10-K", "fp": "FY", "fy": 2024, "filed": "2024-11-01"},
                {"start": "2024-09-29", "end": "2025-09-27", "val": 429000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "NetIncomeLoss": _fact("Net income", "USD", [
                {"start": "2024-09-29", "end": "2025-09-27", "val": 100000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "OperatingIncomeLoss": _fact("Operating income", "USD", [
                {"start": "2024-09-29", "end": "2025-09-27", "val": 125000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "Assets": _fact("Assets", "USD", [
                {"end": "2025-09-27", "val": 360000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "Liabilities": _fact("Liabilities", "USD", [
                {"end": "2025-09-27", "val": 300000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "StockholdersEquity": _fact("Equity", "USD", [
                {"end": "2025-09-27", "val": 60000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "CashAndCashEquivalentsAtCarryingValue": _fact("Cash", "USD", [
                {"end": "2025-09-27", "val": 35000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "NetCashProvidedByUsedInOperatingActivities": _fact("OCF", "USD", [
                {"start": "2024-09-29", "end": "2025-09-27", "val": 130000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "PaymentsToAcquirePropertyPlantAndEquipment": _fact("Capex", "USD", [
                {"start": "2024-09-29", "end": "2025-09-27", "val": 12000000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
            "EarningsPerShareDiluted": _fact("EPS", "USD/shares", [
                {"start": "2024-09-29", "end": "2025-09-27", "val": 6.75, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ]),
        },
        "dei": {
            "EntityCommonStockSharesOutstanding": _fact("Shares", "shares", [
                {"end": "2025-09-27", "val": 14800000000, "form": "10-K", "fp": "FY", "fy": 2025, "filed": "2025-10-31"},
            ])
        },
    },
}


def test_sec_directory_and_company_facts_are_normalized():
    def handler(url, params, headers):
        assert "Ledger/2.0" in headers["User-Agent"]
        if url.endswith("company_tickers_exchange.json"):
            return DIRECTORY
        if url.endswith("/api/xbrl/companyfacts/CIK0000320193.json"):
            return COMPANY_FACTS
        raise AssertionError(url)

    provider = SecProvider("Ledger/2.0 test@example.com", http=FakeJsonHttpClient(handler))

    symbols = provider.list_symbols()
    result = provider.get_fundamentals("AAPL")

    assert symbols[0].cik == "0000320193"
    assert result["company_name"] == "Apple Inc."
    assert result["revenue"] == 429000000000
    assert result["revenue_growth_yoy"] == pytest.approx(0.1)
    assert result["net_margin"] == pytest.approx(100000000000 / 429000000000)
    assert result["free_cash_flow"] == 118000000000
    assert result["eps_diluted"] == 6.75
    assert result["shares_outstanding"] == 14800000000


def test_sec_requires_declared_contact_user_agent():
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SecProvider("Ledger/2.0 your-email@example.com")
