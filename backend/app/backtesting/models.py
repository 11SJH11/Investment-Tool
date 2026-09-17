from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class EntrySignal:
    direction: Direction
    stop_loss: float | None
    take_profit: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # Market entries preserve the original engine contract (next bar open). A
    # limit entry remains pending until a later primary bar touches the price.
    order_type: Literal["market", "limit"] = "market"
    entry_price: float | None = None
    max_wait_bars: int | None = None
    # Optional next-open constraints. Existing strategies retain their contract.
    min_open_exclusive: float | None = None
    max_open_inclusive: float | None = None
    max_stop_distance_pct: float | None = None
    target_r: float | None = None
    rejection_reason: str | None = None
    fill_time_filters_only: bool = False


@dataclass(frozen=True)
class ExitSignal:
    reason: str = "strategy_exit"


@dataclass(frozen=True)
class ManagePositionSignal:
    """Point-in-time position-management instruction.

    Management decisions are created after a completed bar and applied at the
    next primary-bar open, just like discretionary exits. Protective stop/target
    orders that are already active remain intrabar orders handled by the engine.
    """

    new_stop_loss: float | None = None
    new_take_profit: float | None = None
    reduce_fraction: float | None = None
    reason: str = "strategy_manage"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str
    direction: Direction
    entry_time: datetime
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit: float | None
    initial_risk_per_share: float
    initial_risk_amount: float
    entry_commission: float = 0.0
    signal_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    contract_multiplier: float = 1.0
    tick_size: float | None = None
    quantity_step: float | None = None
    initial_quantity: float | None = None
    realized_gross: float = 0.0
    exit_commissions: float = 0.0
    weighted_exit_value: float = 0.0
    exited_quantity: float = 0.0
    partial_exits: list[dict[str, Any]] = field(default_factory=list)
    initial_stop_loss: float | None = None
    initial_take_profit: float | None = None

    def __post_init__(self) -> None:
        if self.initial_quantity is None:
            self.initial_quantity = float(self.quantity)
        if self.initial_stop_loss is None:
            self.initial_stop_loss = float(self.stop_loss)
        if self.initial_take_profit is None and self.take_profit is not None:
            self.initial_take_profit = float(self.take_profit)

    @property
    def notional(self) -> float:
        """Current open notional used for leverage/exposure checks."""
        return abs(self.entry_price * self.quantity * self.contract_multiplier)

    @property
    def initial_notional(self) -> float:
        return abs(self.entry_price * float(self.initial_quantity or 0.0) * self.contract_multiplier)


@dataclass
class BacktestTrade:
    symbol: str
    direction: Direction
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    stop_loss: float
    take_profit: float | None
    initial_risk_amount: float
    gross_pnl: float
    fees: float
    net_pnl: float
    pnl_pct: float | None
    r_multiple: float | None
    planned_rr: float | None
    result: str
    exit_reason: str
    signal_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestConfig:
    starting_balance: float = 10_000.0
    sizing_mode: Literal["risk_pct", "cash_risk", "quantity", "cash_position", "position_pct"] = "risk_pct"
    risk_value: float = 1.0
    commission_per_order: float = 0.0
    slippage_bps: float = 0.0
    # Full assumed quoted spread in basis points. The engine applies half the
    # spread adversely on entry and half adversely on exit.
    spread_bps: float = 0.0
    max_leverage: float = 1.0
    max_open_positions: int = 5
    same_bar_policy: Literal["stop_first", "target_first"] = "stop_first"

    # Entry filters are interpreted in exchange-local time. Windows are
    # start-inclusive/end-exclusive and control new fills, not management of an
    # already-open position.
    entry_windows: tuple[tuple[str, str], ...] = ()
    trading_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # Monday=0
    exchange_timezone: str = "America/New_York"
    session_end: str = "16:00"

    # If False, positions are closed at force_close_time or the configured
    # session end and no entry is allowed to roll into the next session.
    allow_overnight: bool = True
    force_close_time: str | None = None

    # Account/session guardrails. None/0 disables a guardrail.
    max_trades_per_day: int | None = None
    max_daily_loss_r: float | None = None
    max_consecutive_losses: int | None = None
    cooldown_minutes: int = 0
