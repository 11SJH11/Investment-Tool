from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Any, Literal

from app.backtesting.context import StrategyContext
from app.backtesting.models import EntrySignal, ExitSignal, ManagePositionSignal


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    kind: Literal["int", "float", "bool", "choice", "string"]
    default: int | float | str | bool
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class StrategySpec:
    key: str
    name: str
    description: str = ""
    defaults: dict[str, int | float | str | bool] = field(default_factory=dict)
    timeframes: tuple[str, ...] = ("1d",)
    # Ordinary strategy inputs that are intentionally configurable run-to-run.
    parameters: tuple[ParameterSpec, ...] = ()
    # Strategy-owned values that are hidden from normal runs but may be
    # temporarily overridden by research tools such as parameter sensitivity.
    # This lets a strategy keep stop/target/management rules in code while still
    # allowing robustness testing without permanently editing the source file.
    research_parameters: tuple[ParameterSpec, ...] = ()
    category: str = "Reference"
    risk_management: dict[str, str] = field(default_factory=dict)
    source_file: str = ""


class Strategy(ABC):
    """Plugin contract for point-in-time backtest strategies.

    Strategies decide *what* should happen. The engine owns fills, account risk
    sizing, slippage, commissions, stop/target execution and performance
    accounting. ``research_parameters`` are temporary overrides used only when a
    research workflow explicitly requests them.
    """

    spec: StrategySpec

    def __init__(self, **params):
        defaults = dict(self.spec.defaults)
        defaults.update({p.key: p.default for p in self.spec.research_parameters})
        self.params = {**defaults, **params}

    def reset(self) -> None:
        """Reset mutable strategy state before a new symbol/run."""

    def on_bar(self, ctx: StrategyContext) -> EntrySignal | ExitSignal | ManagePositionSignal | None:
        return None
