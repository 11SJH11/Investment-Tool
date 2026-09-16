from dataclasses import dataclass
from typing import Protocol


class BrokerHistoryError(RuntimeError):
    """A sanitized error suitable for sync status and the user interface."""


@dataclass
class HistoryBatch:
    trades: list[dict]
    cursor: str


class BrokerHistory(Protocol):
    provider: str
    account_key: str
    environment: str
    account_label: str

    def fetch_closed(self, cursor: str | None) -> HistoryBatch: ...

    def close(self) -> None: ...
