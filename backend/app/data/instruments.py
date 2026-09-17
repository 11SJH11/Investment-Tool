from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from app.data.futures import FAMILIES


@dataclass(frozen=True)
class InstrumentSpec:
    ticker: str
    name: str
    asset_type: str
    security_type: str
    provider_key: str
    provider_symbol: str
    session_profile: str
    exchange: str | None = None
    root: str | None = None
    continuous_rank: int | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        family = FAMILIES.get(self.root)
        if family:
            data.update(family.as_dict())
            data["exchange"] = family.exchange
        if self.asset_type == "future":
            data["execution_supported"] = bool(family and self.security_type == "future_contract")
            data["data_availability"] = "Subject to Massive contract coverage and account entitlement; live coverage not verified"
        return data


# Keep this list deliberately small: these are aliases Ledger explicitly promises
# in the UI. Dated futures remain accepted by the backend even when they are not
# advertised by SymbolSearch yet.
_VIRTUAL: dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec(
        ticker="XAUUSD",
        name="Gold / U.S. Dollar (OANDA)",
        asset_type="spot_metal",
        security_type="spot_metal",
        provider_key="oanda",
        provider_symbol="XAU_USD",
        session_profile="oanda_24h",
        exchange="OANDA",
    ),
    "NQ1!": InstrumentSpec(
        ticker="NQ1!",
        name="E-mini Nasdaq-100 Continuous Front Contract",
        asset_type="future",
        security_type="continuous_future",
        provider_key="massive",
        provider_symbol="NQ1!",
        session_profile="futures_24h",
        exchange="CME",
        root="NQ",
        continuous_rank=1,
    ),
}

for _root, _family in FAMILIES.items():
    _alias = f"{_root}1!"
    _VIRTUAL[_alias] = InstrumentSpec(_alias, f"{_family.description} Continuous Front Contract",
        "future", "continuous_future", "massive", _alias, "futures_24h", _family.exchange, _root, 1)

_CONTINUOUS_RE = re.compile(r"^(?P<root>[A-Z][A-Z0-9]{0,4})(?P<rank>[1-9])!$")
# Standard futures month codes + one/two digit year suffix. This intentionally
# routes only symbols that actually look like dated futures contracts.
_DATED_FUTURE_RE = re.compile(r"^(?P<root>[A-Z][A-Z0-9]{0,4})(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{1,2})$")


def normalize_symbol(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if symbol == "XAU_USD":
        return "XAUUSD"
    return symbol


def instrument_spec(ticker: str) -> InstrumentSpec:
    symbol = normalize_symbol(ticker)
    if symbol in _VIRTUAL:
        return _VIRTUAL[symbol]

    continuous = _CONTINUOUS_RE.fullmatch(symbol)
    if continuous:
        root = continuous.group("root")
        rank = int(continuous.group("rank"))
        return InstrumentSpec(
            ticker=symbol,
            name=f"{root} continuous futures contract #{rank}",
            asset_type="future",
            security_type="continuous_future",
            provider_key="massive",
            provider_symbol=symbol,
            session_profile="futures_24h",
            exchange=FAMILIES[root].exchange if root in FAMILIES else None,
            root=root,
            continuous_rank=rank,
        )

    dated = _DATED_FUTURE_RE.fullmatch(symbol)
    if dated:
        root = dated.group("root")
        return InstrumentSpec(
            ticker=symbol,
            name=f"{symbol} futures contract",
            asset_type="future",
            security_type="future_contract",
            provider_key="massive",
            provider_symbol=symbol,
            session_profile="futures_24h",
            exchange=FAMILIES[root].exchange if root in FAMILIES else None,
            root=root,
        )

    return InstrumentSpec(
        ticker=symbol,
        name=symbol,
        asset_type="equity",
        security_type="common_stock",
        provider_key="alpaca",
        provider_symbol=symbol,
        session_profile="us_equity",
    )


def virtual_symbols(query: str = "") -> list[dict]:
    needle = str(query or "").strip().upper()
    output: list[dict] = []
    for spec in _VIRTUAL.values():
        if needle and needle not in spec.ticker.upper() and needle not in spec.name.upper():
            continue
        output.append(
            {
                "ticker": spec.ticker,
                "name": spec.name,
                "asset_type": spec.asset_type,
                "security_type": spec.security_type,
                "exchange": spec.exchange,
                "status": "active",
                "tradable": None,
                "fractionable": None,
                "shortable": None,
                "provider": spec.provider_key,
                "provider_id": spec.provider_symbol,
                "cik": None,
            }
        )
    return output


def virtual_symbol(ticker: str) -> dict | None:
    symbol = normalize_symbol(ticker)
    matches = [item for item in virtual_symbols(symbol) if item["ticker"] == symbol]
    return matches[0] if matches else None
