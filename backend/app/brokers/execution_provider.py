"""Execution boundary for future integration. This phase cannot submit orders.
Backtest sizing is not a live risk engine. No adapter may bypass that missing gate.
"""
from dataclasses import dataclass
from typing import Protocol
from app.brokers.base import BrokerHistoryError

@dataclass(frozen=True)
class ExecutionCapabilities:
    equities: bool=False
    options: bool=False
    crypto: bool=False
    futures: bool=False
    fractional: bool=False
    market_orders: bool=False
    limit_orders: bool=False
    enabled: bool=False

class ExecutionProvider(Protocol):
    def capabilities(self) -> ExecutionCapabilities: ...
    def submit(self, order, risk_approval): ...

class ReadOnlyExecutionDestination:
    def __init__(self,provider):self.provider=provider
    def capabilities(self):return ExecutionCapabilities()
    def submit(self,order,risk_approval=None):
        raise BrokerHistoryError('Ledger live execution is disabled: an audited live risk gateway and account/instrument permissions are required',category='capability')
