from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.data.http import JsonHttpClient
from app.data.providers.base import MarketDataProvider, Quote, SecurityMasterProvider, Symbol, Timeframe
from app.data.security_types import infer_security_type


_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "30m": "30Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
    "1w": "1Week",
}


class AlpacaProvider(SecurityMasterProvider, MarketDataProvider):
    key = "alpaca"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        historical_feed: str = "sip",
        live_feed: str = "iex",
        adjustment: str = "split",
        historical_delay_minutes: int = 15,
        trading_base_url: str = "https://paper-api.alpaca.markets",
        data_base_url: str = "https://data.alpaca.markets",
        http: JsonHttpClient | None = None,
    ):
        if not api_key or not api_secret:
            raise ValueError("Alpaca API key and secret are required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.historical_feed = historical_feed
        self.live_feed = live_feed
        self.adjustment = adjustment
        self.historical_delay_minutes = max(0, historical_delay_minutes)
        self.trading_base_url = trading_base_url.rstrip("/")
        self.data_base_url = data_base_url.rstrip("/")
        self.http = http or JsonHttpClient()
        self.cache_namespace = f"alpaca-{self.historical_feed}-{self.adjustment}"

    @property
    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }

    def list_symbols(self) -> list[Symbol]:
        payload = self.http.get_json(
            f"{self.trading_base_url}/v2/assets",
            params={"status": "active", "asset_class": "us_equity"},
            headers=self.headers,
        )
        symbols: list[Symbol] = []
        for asset in payload:
            ticker = str(asset.get("symbol") or "").strip().upper()
            if not ticker:
                continue
            symbols.append(
                Symbol(
                    ticker=ticker,
                    name=str(asset.get("name") or ticker),
                    asset_type="equity",
                    security_type=infer_security_type(str(asset.get("name") or ticker), ticker),
                    exchange=asset.get("exchange"),
                    status=asset.get("status"),
                    tradable=_optional_bool(asset.get("tradable")),
                    fractionable=_optional_bool(asset.get("fractionable")),
                    shortable=_optional_bool(asset.get("shortable")),
                    provider_id=asset.get("id"),
                )
            )
        return symbols

    def get_quote(self, ticker: str) -> Quote:
        symbol = ticker.strip().upper()
        payload = self.http.get_json(
            f"{self.data_base_url}/v2/stocks/{symbol}/bars/latest",
            params={"feed": self.live_feed},
            headers=self.headers,
        )
        bar = payload.get("bar") or {}
        if bar.get("c") is None or not bar.get("t"):
            raise RuntimeError(f"No latest bar returned for {symbol}")
        return Quote(
            ticker=symbol,
            price=float(bar["c"]),
            timestamp=_parse_timestamp(bar["t"]),
        )

    def get_latest_bars(self, tickers: list[str]) -> list[dict[str, Any]]:
        symbols = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
        if not symbols:
            return []
        payload = self.http.get_json(
            f"{self.data_base_url}/v2/stocks/bars/latest",
            params={"symbols": ",".join(symbols), "feed": self.live_feed},
            headers=self.headers,
        )
        bars = payload.get("bars") or {}
        result: list[dict[str, Any]] = []
        for symbol, bar in bars.items():
            if bar.get("c") is None or not bar.get("t"):
                continue
            result.append({
                "ticker": symbol.upper(),
                "price": float(bar["c"]),
                "timestamp": str(bar["t"]),
            })
        return result

    def get_bars(
        self,
        ticker: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        symbol = ticker.strip().upper()
        if self.historical_feed == "sip" and self.historical_delay_minutes > 0:
            from datetime import timedelta

            latest_allowed = datetime.now(timezone.utc) - timedelta(minutes=self.historical_delay_minutes)
            effective_end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
            if effective_end.astimezone(timezone.utc) > latest_allowed:
                raise ValueError(
                    f"Historical SIP data on the configured plan is delayed by "
                    f"{self.historical_delay_minutes} minutes; choose an earlier end time "
                    "or set ALPACA_HISTORICAL_DELAY_MINUTES=0 after upgrading your data plan."
                )
        alpaca_timeframe = _TIMEFRAME_MAP.get(timeframe)
        if alpaca_timeframe is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        bars: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "timeframe": alpaca_timeframe,
                "start": _as_rfc3339(start),
                "end": _as_rfc3339(end),
                "limit": 10000,
                "feed": self.historical_feed,
                "adjustment": self.adjustment,
                "sort": "asc",
            }
            if page_token:
                params["page_token"] = page_token
            payload = self.http.get_json(
                f"{self.data_base_url}/v2/stocks/{symbol}/bars",
                params=params,
                headers=self.headers,
            )
            bars.extend(payload.get("bars") or [])
            page_token = payload.get("next_page_token")
            if not page_token:
                break

        if not bars:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        frame = pd.DataFrame(
            {
                "timestamp": [bar.get("t") for bar in bars],
                "open": [bar.get("o") for bar in bars],
                "high": [bar.get("h") for bar in bars],
                "low": [bar.get("l") for bar in bars],
                "close": [bar.get("c") for bar in bars],
                "volume": [bar.get("v") for bar in bars],
            }
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame.dropna(subset=["timestamp", "open", "high", "low", "close"]).reset_index(drop=True)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _as_rfc3339(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
