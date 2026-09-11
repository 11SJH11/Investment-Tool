from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pandas as pd


Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


@dataclass(frozen=True)
class Symbol:
    ticker: str
    name: str
    asset_type: str = "equity"
    security_type: str = "common_stock"
    exchange: str | None = None
    status: str | None = None
    tradable: bool | None = None
    fractionable: bool | None = None
    shortable: bool | None = None
    provider_id: str | None = None
    cik: str | None = None


@dataclass(frozen=True)
class Quote:
    ticker: str
    price: float
    timestamp: datetime


class SecurityMasterProvider(ABC):
    key: str

    @abstractmethod
    def list_symbols(self) -> list[Symbol]: ...


class MarketDataProvider(ABC):
    key: str
    cache_namespace: str

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote: ...

    @abstractmethod
    def get_bars(
        self,
        ticker: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame: ...


class FundamentalsProvider(ABC):
    key: str

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> dict: ...


class MacroDataProvider(ABC):
    key: str

    @abstractmethod
    def get_snapshot(self) -> dict: ...


class NewsProvider(ABC):
    key: str

    @abstractmethod
    def get_news(
        self,
        tickers: list[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict]: ...


class EconomicCalendarProvider(ABC):
    key: str

    @abstractmethod
    def get_events(self, start: datetime, end: datetime) -> list[dict]: ...
