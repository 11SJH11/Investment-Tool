"""Canonical read-only execution evidence. Money is reported, never inferred.

Quantity retains the provider unit (lots/shares/units); contract economics must
not be guessed from a symbol. Order aggregates are explicitly not deal fills.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from app.brokers.base import BrokerHistoryError


def number(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError()
        return result
    except (ValueError, InvalidOperation):
        raise BrokerHistoryError('Broker history contains invalid numeric facts') from None


def identity(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        raise BrokerHistoryError('Broker history lacks a stable identity')
    return str(value)


def account_key(provider, environment, server, account_id):
    # Length-safe components avoid delimiter collisions. Never exposed raw.
    import json
    return sha256(json.dumps([provider, environment, server, identity(account_id)]).encode()).hexdigest()


def utc_millis(value):
    try:
        return datetime.fromtimestamp(float(number(value) / 1000), timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise BrokerHistoryError('Broker history contains an invalid timestamp') from None


@dataclass(frozen=True)
class Execution:
    provider: str
    environment: str
    account_key: str
    external_id: str
    order_id: str
    position_id: str
    symbol: str
    asset_class: str
    side: str
    quantity: str
    price: str
    timestamp: str
    quantity_unit: str
    role: str = 'net'  # entry/exit for MT5, signed position flow for order aggregates
    evidence: str = 'deal'
    commission: str | None = None  # signed cash impact: negative cost, positive rebate
    swap: str | None = None
    fee: str | None = None
    realized_pnl: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        for value in (self.provider, self.environment, self.account_key, self.external_id,
                      self.order_id, self.symbol, self.quantity_unit):
            identity(value)
        if self.position_id:
            identity(self.position_id)
        if self.side not in {'buy', 'sell'} or self.role not in {'net', 'entry', 'exit'}:
            raise BrokerHistoryError('Broker execution direction or entry type is unsupported')
        if number(self.quantity) <= 0 or number(self.price) <= 0:
            raise BrokerHistoryError('Broker execution size or price is invalid')
        for value in (self.commission, self.swap, self.fee, self.realized_pnl):
            if value is not None:
                number(value)
        try:
            stamp = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError()
            object.__setattr__(self, 'timestamp', stamp.astimezone(timezone.utc).isoformat())
        except (ValueError, TypeError):
            raise BrokerHistoryError('Broker execution requires a timezone-aware timestamp') from None

    def payload(self):
        return asdict(self)


@dataclass
class ExecutionBatch:
    executions: list[Execution]
    cursor: str
    open_position_ids: set[str] = field(default_factory=set)


def closed_positions(executions, account_label, currency, open_position_ids=()):
    """One fully evidenced position -> one Journal row; partials remain evidence.

    Reversals/reused position IDs and ambiguous simultaneous opposing aggregates
    fail closed. No FIFO, lot multiplier, FX rate or initial risk is invented.
    """
    groups = {}
    for execution in executions:
        if not execution.position_id:
            raise BrokerHistoryError('Position identity is required before creating a Journal trade')
        groups.setdefault(execution.position_id, []).append(execution)
    trades = []
    for position_id, fills in groups.items():
        fills.sort(key=lambda e: (e.timestamp, (0, int(e.external_id)) if e.external_id.isdecimal() else (1, e.external_id)))
        first = fills[0]
        if first.evidence == 'order_aggregate':
            earliest_created = min(number(e.metadata['createdDate']) for e in fills)
            first_sides = {e.side for e in fills if number(e.metadata['createdDate']) == earliest_created}
            if first_sides != {first.side}:
                raise BrokerHistoryError('Order lifecycle chronology is ambiguous; direction was not guessed')
        if len({(e.provider, e.environment, e.account_key, e.symbol, e.quantity_unit) for e in fills}) != 1:
            raise BrokerHistoryError('Position history contains conflicting instrument or account facts')
        balance = Decimal(0)
        entries, exits = [], []
        for index, e in enumerate(fills):
            if index and balance == 0:
                raise BrokerHistoryError('Reused or reversed position history needs manual reconciliation')
            if e.evidence == 'order_aggregate' and any(
                x.timestamp == e.timestamp and x.side != e.side for x in fills):
                raise BrokerHistoryError('Order aggregate chronology is ambiguous; history was preserved')
            opening = e.side == first.side
            if e.role == 'entry' and not opening or e.role == 'exit' and opening:
                raise BrokerHistoryError('Position entry/exit history does not reconcile')
            if not index and e.role == 'exit':
                raise BrokerHistoryError('Position opening history is missing; cursor was preserved')
            balance += number(e.quantity) * (1 if opening else -1)
            if balance < 0:
                raise BrokerHistoryError('Position history is incomplete or contains an unsupported reversal')
            (entries if opening else exits).append(e)
        if balance != 0 or position_id in open_position_ids:
            continue
        quantity = sum((number(e.quantity) for e in entries), Decimal(0))
        avg = lambda items: float(sum((number(e.quantity) * number(e.price) for e in items), Decimal(0)) / quantity)
        total = lambda key: (sum((number(getattr(e, key)) for e in fills), Decimal(0))
                             if all(getattr(e, key) is not None for e in fills) else None)
        realized, commission, swap, fee = [total(k) for k in ('realized_pnl', 'commission', 'swap', 'fee')]
        complete = all(v is not None for v in (realized, commission, swap, fee))
        net = realized + commission + swap + fee if complete else None
        money = lambda v: float(v) if v is not None else None
        # Only entry evidence from the official adapter establishes automation.
        # SL/TP closes and magic numbers alone never establish strategy origin.
        automated = any(e.metadata.get('programmatic_order') is True for e in entries)
        trades.append(dict(source='broker_' + first.provider, external_provider=first.provider,
            is_automated=True if automated else None, execution_source='imported',
            external_account_key=first.account_key,
            external_id=f'{first.environment}:{first.account_key}:{position_id}',
            external_order_id=first.order_id, account=account_label,
            name=first.provider + ' imported position', ticker=first.symbol,
            direction='long' if first.side == 'buy' else 'short', status='closed',
            opened_at=first.timestamp, closed_at=fills[-1].timestamp,
            entry_price=avg(entries), exit_price=avg(exits), quantity=float(quantity),
            account_currency=currency, position_currency=currency,
            broker_realized_pnl=money(realized), pnl_amount=money(net),
            commission=money(-commission if commission is not None else None),
            financing=money(swap), fees=money(-(commission + fee) if complete else None),
            costs_complete=complete, pnl_source='broker_reported',
            result=('win' if net > 0 else 'loss' if net < 0 else 'breakeven') if net is not None else None,
            source_metadata=dict(canonical_execution_version=1, environment=first.environment, position_id=position_id,
                quantity_unit=first.quantity_unit, asset_class=first.asset_class,
                executions=[e.payload() for e in fills], costs_complete=complete,
                timestamp_basis='order_last_modified' if first.evidence == 'order_aggregate' else 'execution',
                cost_note=None if complete else 'Provider did not supply complete attributable costs/P&L'),
            imported_at=datetime.now(timezone.utc).isoformat()))
    return trades
