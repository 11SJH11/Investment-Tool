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

PROVENANCE_COLUMNS = ["continuous_alias", "provider", "adjustment_mode", "session_end_date", "source_contract", "roll_method", "roll_schedule_version",
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


def validate_execution_symbol(symbol):
    from app.data.instruments import instrument_spec
    spec = instrument_spec(symbol)
    if spec.security_type == 'continuous_future':
        if spec.continuous_rank != 1 or spec.root not in FAMILIES:
            raise ValueError('Continuous execution requires a supported front-contract family')
        return
    execution_economics(symbol)


def execution_contract(symbol, bar):
    """Resolve only raw, provenance-backed dated prices. Never infer a contract."""
    from app.data.instruments import instrument_spec
    spec = instrument_spec(symbol)
    if spec.asset_type != 'future':
        return symbol
    validate_execution_symbol(symbol)
    if bar.get('adjustment_method', 'none') != 'none' or bar.get('adjustment_mode', 'raw') != 'raw' or float(bar.get('price_adjustment', 0)) != 0:
        raise ValueError('Futures execution requires unadjusted dated-contract prices')
    source = bar.get('source_contract', symbol)
    if spec.security_type == 'continuous_future':
        dated = instrument_spec(source)
        if (dated.security_type != 'future_contract' or dated.root != spec.root
                or bar.get('continuous_alias') != spec.ticker or bar.get('provider') != 'massive'
                or bar.get('roll_schedule_version') not in {'prior-session-volume45-v1','calendar-front-v1'}):
            raise ValueError('Continuous execution requires verified raw source-contract provenance; refresh the data')
    elif source != spec.ticker:
        raise ValueError('Futures execution cannot cross source contracts')
    execution_economics(source)
    return source


def validate_execution_frame(symbol, frame):
    from app.data.instruments import instrument_spec
    validate_execution_symbol(symbol)
    if instrument_spec(symbol).asset_type != 'future' or frame.empty:
        return
    columns = [c for c in PROVENANCE_COLUMNS if c in frame]
    records = frame[columns].drop_duplicates().to_dict('records') if columns else [{}]
    for row in records:
        execution_contract(symbol,row)
