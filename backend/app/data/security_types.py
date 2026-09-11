from __future__ import annotations


SECURITY_TYPES = {
    "common_stock",
    "adr",
    "reit",
    "etf",
    "etn",
    "spac",
    "preferred",
    "unit",
    "warrant",
    "right",
    "fund",
    "other",
}


def infer_security_type(name: str, ticker: str = "") -> str:
    """Best-effort classification from the security master display name.

    Alpaca's US asset master identifies the asset class as ``us_equity`` but does
    not provide the finer instrument category Ledger needs for screening.  Keep
    this heuristic isolated so it can later be replaced/enriched by a dedicated
    reference-data provider without changing the screener or UI.
    """
    text = f" {str(name or '').upper()} "
    symbol = str(ticker or "").upper()

    if "WARRANT" in text or symbol.endswith("W") and "WARRANT" in text:
        return "warrant"
    if " UNITS " in text or " UNIT " in text:
        return "unit"
    if " RIGHTS " in text or " RIGHT " in text:
        return "right"
    if " PREFERRED " in text or " PREFERENCE " in text:
        return "preferred"
    if "ACQUISITION CORP" in text or "ACQUISITION CO" in text or "BLANK CHECK" in text:
        return "spac"
    if "AMERICAN DEPOSITARY" in text or "AMERICAN DEPOSITORY" in text or " ADR " in text:
        return "adr"
    if "REAL ESTATE INVESTMENT TRUST" in text or " REIT " in text:
        return "reit"
    if " ETF " in text or text.rstrip().endswith(" ETF") or "EXCHANGE TRADED FUND" in text:
        return "etf"
    if " ETN " in text or text.rstrip().endswith(" ETN") or "EXCHANGE TRADED NOTE" in text:
        return "etn"
    if " FUND " in text or " FUNDS " in text:
        return "fund"
    return "common_stock"


def security_type_label(value: str) -> str:
    return {
        "stock": "Stocks",
        "common_stock": "Common stock",
        "adr": "ADR / depositary share",
        "reit": "REIT",
        "etf": "ETF",
        "etn": "ETN",
        "spac": "SPAC",
        "preferred": "Preferred",
        "unit": "Unit",
        "warrant": "Warrant",
        "right": "Right",
        "fund": "Fund",
        "other": "Other",
    }.get(value, value.replace("_", " ").title())
