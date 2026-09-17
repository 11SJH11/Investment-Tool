"""Versioned contract economics; exchange calendars remain provider-owned."""
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR


@dataclass(frozen=True)
class FuturesFamily:
    root: str
    description: str
    exchange: str
    tick_size: float
    contract_multiplier: float
    expiry_convention: str
    currency: str = "USD"
    session: str = "Sun-Fri 18:00-17:00 America/New_York; daily 17:00-18:00 break; exchange holidays apply"
    specification_version: str = "cme-economics-v1"

    def as_dict(self):
        return {**asdict(self), "point_value": self.contract_multiplier,
                "tick_value": self.tick_size * self.contract_multiplier,
                "provider_product_code": self.root, "quantity_step": 1}


_QUARTERLY = "Mar/Jun/Sep/Dec; third-Friday cash settlement; provider contract dates authoritative"
_GOLD = "Exchange-listed delivery months; third-last business-day termination; provider contract dates authoritative"
_CRUDE = "Monthly; CL exchange business-day rule before prior-month 25th; MCL one business day before CL; provider dates authoritative"
FAMILIES = {row.root: row for row in (
    FuturesFamily("NQ", "E-mini Nasdaq-100", "CME", .25, 20, _QUARTERLY),
    FuturesFamily("MNQ", "Micro E-mini Nasdaq-100", "CME", .25, 2, _QUARTERLY),
    FuturesFamily("ES", "E-mini S&P 500", "CME", .25, 50, _QUARTERLY),
    FuturesFamily("MES", "Micro E-mini S&P 500", "CME", .25, 5, _QUARTERLY),
    FuturesFamily("YM", "E-mini Dow", "CBOT", 1, 5, _QUARTERLY),
    FuturesFamily("MYM", "Micro E-mini Dow", "CBOT", 1, .5, _QUARTERLY),
    FuturesFamily("RTY", "E-mini Russell 2000", "CME", .1, 50, _QUARTERLY),
    FuturesFamily("M2K", "Micro E-mini Russell 2000", "CME", .1, 5, _QUARTERLY),
    FuturesFamily("GC", "Gold", "COMEX", .1, 100, _GOLD),
    FuturesFamily("MGC", "Micro Gold", "COMEX", .1, 10, _GOLD),
    FuturesFamily("CL", "WTI Crude Oil", "NYMEX", .01, 1000, _CRUDE),
    FuturesFamily("MCL", "Micro WTI Crude Oil", "NYMEX", .01, 100, _CRUDE),
)}

PROVENANCE_COLUMNS = ["source_contract", "roll_method", "roll_schedule_version",
                      "contract_last_trade_date", "roll_effective_at", "adjustment_method", "price_adjustment"]


def on_tick(price, tick):
    return tick is None or abs(float(price) / tick - round(float(price) / tick)) < 1e-7


def adverse_tick(price, tick, direction, *, entering):
    if tick is None:
        return float(price)
    up = (direction == "long") == entering
    units = Decimal(str(price)) / Decimal(str(tick))
    return float(units.to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * Decimal(str(tick)))


def execution_economics(symbol):
    from app.data.instruments import instrument_spec
    spec = instrument_spec(symbol)
    if spec.asset_type != "future":
        return 1.0, None, None
    if spec.security_type == "continuous_future":
        raise ValueError("Continuous futures are chart-only: select a dated contract for execution; cross-roll fills are not modelled")
    family = FAMILIES.get(spec.root)
    if family is None:
        raise ValueError("Futures execution requires a verified contract family")
    return family.contract_multiplier, family.tick_size, 1.0
