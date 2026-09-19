from dataclasses import dataclass
from typing import Protocol


class BrokerHistoryError(RuntimeError):
    """A sanitized error suitable for sync status and the user interface."""
    def __init__(self, message, *, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code, self.retry_after = status_code, retry_after


@dataclass
class HistoryBatch:
    trades: list[dict]
    cursor: str


class BrokerHistoryAdapter(Protocol):
    provider: str
    account_key: str
    environment: str
    account_label: str

    def capability_report(self) -> dict: ...

    def accounts(self) -> list[dict]: ...

    def fetch_closed(self, cursor: str | None) -> HistoryBatch: ...

    def close(self) -> None: ...


# Existing imports retain the same contract. HistoryBatch owns normalized Journal
# facts; repositories own cursors and discretionary review, not adapters.
BrokerHistory = BrokerHistoryAdapter
