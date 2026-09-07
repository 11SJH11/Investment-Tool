from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

import pandas as pd

from app.data.http import JsonHttpClient
from app.data.instruments import instrument_spec, normalize_symbol
from app.data.providers.base import MarketDataProvider, Quote, Timeframe


_RESOLUTION_MAP: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour",
    "1d": "1session",
    "1w": "1week",
}


@dataclass(frozen=True)
class FutureContract:
    ticker: str
    product_code: str
    first_trade_date: date
    last_trade_date: date


class MassiveFuturesProvider(MarketDataProvider):
    key = "massive"
    historical_delay_minutes = 0
    historical_feed = "massive-futures"
    adjustment = None

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.massive.com",
        back_adjust: bool = False,
        http: JsonHttpClient | None = None,
    ):
        if not api_key:
            raise ValueError("Massive API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.back_adjust = bool(back_adjust)
        self.http = http or JsonHttpClient()
        adjustment = "back-adjusted" if self.back_adjust else "unadjusted"
        # Calendar roll is intentionally named in the namespace so a later
        # volume-derived roll policy cannot accidentally reuse incompatible cache.
        self.cache_namespace = f"massive-futures-calendar-front-{adjustment}-v1"

    def get_quote(self, ticker: str) -> Quote:
        now = datetime.now(timezone.utc)
        frame = self.get_bars(ticker, "1m", now - timedelta(days=5), now)
        if frame.empty:
            raise RuntimeError(f"No Massive futures bars returned for {ticker}")
        row = frame.iloc[-1]
        ts = pd.Timestamp(row["timestamp"]).to_pydatetime()
        return Quote(ticker=normalize_symbol(ticker), price=float(row["close"]), timestamp=ts)

    def get_bars(self, ticker: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        symbol = normalize_symbol(ticker)
        resolution = _RESOLUTION_MAP.get(timeframe)
        if resolution is None:
            raise ValueError(f"Unsupported Massive futures timeframe: {timeframe}")
        start = _utc(start)
        end = _utc(end)
        if start >= end:
            return _empty()

        spec = instrument_spec(symbol)
        if spec.security_type == "continuous_future":
            if spec.continuous_rank != 1:
                raise ValueError("Phase 6.2 currently supports only front-contract continuous aliases such as NQ1!")
            frame = self._continuous_front(spec.root or "", resolution, start, end)
            return _back_adjust(frame) if self.back_adjust else frame
        return self._contract_bars(symbol, resolution, start, end, source_contract=symbol)

    def list_contracts(self, product_code: str) -> list[FutureContract]:
        root = str(product_code or "").strip().upper()
        if not root:
            raise ValueError("Futures product code is required")
        url = f"{self.base_url}/futures/v1/contracts"
        # Keep the contracts query deliberately conservative. Massive documents
        # product_code and limit for this endpoint, while the richer filters/sorts
        # have changed during the futures API rollout. We sort and filter locally,
        # which avoids a provider-side 400 without changing Ledger semantics.
        params: dict[str, Any] | None = {
            "product_code": root,
            "limit": 1000,
        }
        headers = self._auth_headers()
        rows: list[dict] = []
        while url:
            payload = self.http.get_json(url, params=params, headers=headers)
            rows.extend(payload.get("results") or [])
            next_url = payload.get("next_url")
            url = urljoin(self.base_url + "/", next_url) if next_url else ""
            # Massive's next_url already carries the cursor/query state. With
            # header authentication, no API key ever needs to appear in the URL.
            params = None

        contracts: list[FutureContract] = []
        for item in rows:
            if str(item.get("product_code") or "").upper() != root:
                continue
            contract_type = str(item.get("type") or "").strip().lower()
            if contract_type not in {"", "single"}:
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            first = _parse_date(item.get("first_trade_date"))
            last = _parse_date(item.get("last_trade_date"))
            if not ticker or first is None or last is None:
                continue
            contracts.append(FutureContract(ticker=ticker, product_code=root, first_trade_date=first, last_trade_date=last))
        contracts.sort(key=lambda item: (item.last_trade_date, item.first_trade_date, item.ticker))
        return contracts

    def _auth_headers(self) -> dict[str, str]:
        # Massive supports Bearer authentication. Prefer it over ?apiKey= so
        # tracebacks, access logs and copied URLs cannot expose the credential.
        return {"Authorization": f"Bearer {self.api_key}"}

    def _continuous_front(self, root: str, resolution: str, start: datetime, end: datetime) -> pd.DataFrame:
        contracts = self.list_contracts(root)
        if not contracts:
            raise RuntimeError(f"Massive returned no dated contracts for futures product {root}")

        start_date = start.date()
        end_date = end.date()
        eligible = [c for c in contracts if c.last_trade_date >= start_date and c.first_trade_date <= end_date]
        if not eligible:
            raise RuntimeError(f"No {root} contract overlaps {start_date} to {end_date}")

        # Calendar-front v1: the active front contract is the nearest dated
        # contract whose last-trade date has not passed. This is deterministic and
        # gets NQ1! working now. A later phase will replace this with the planned
        # volume-crossover roll schedule used to more closely match TradingView.
        segments: list[pd.DataFrame] = []
        cursor = start
        for contract in eligible:
            if cursor >= end:
                break
            contract_end = datetime.combine(contract.last_trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
            segment_start = max(cursor, start, datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc))
            segment_end = min(end, contract_end)
            if segment_start >= segment_end:
                continue
            frame = self._contract_bars(contract.ticker, resolution, segment_start, segment_end, source_contract=contract.ticker)
            if not frame.empty:
                segments.append(frame)
            cursor = max(cursor, contract_end)

        if not segments:
            return _empty(include_contract=True)
        output = pd.concat(segments, ignore_index=True)
        return (
            output.drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def _contract_bars(
        self,
        ticker: str,
        resolution: str,
        start: datetime,
        end: datetime,
        *,
        source_contract: str,
    ) -> pd.DataFrame:
        url = f"{self.base_url}/futures/v1/aggs/{ticker}"
        params: dict[str, Any] | None = {
            "resolution": resolution,
            "window_start.gte": _unix_ns(start),
            "window_start.lt": _unix_ns(end),
            "limit": 50000,
            "sort": "window_start.asc",
        }
        headers = self._auth_headers()
        rows: list[dict] = []
        while url:
            payload = self.http.get_json(url, params=params, headers=headers)
            rows.extend(payload.get("results") or [])
            next_url = payload.get("next_url")
            url = urljoin(self.base_url + "/", next_url) if next_url else ""
            params = None

        if not rows:
            return _empty(include_contract=True)
        frame = pd.DataFrame(
            {
                "timestamp": [item.get("window_start") for item in rows],
                "open": [item.get("open") for item in rows],
                "high": [item.get("high") for item in rows],
                "low": [item.get("low") for item in rows],
                "close": [item.get("close") for item in rows],
                "volume": [item.get("volume", 0) for item in rows],
                "source_contract": [source_contract] * len(rows),
            }
        )
        frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["timestamp"], errors="coerce"), unit="ns", utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return (
            frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
            .drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )


def _back_adjust(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "source_contract" not in frame.columns:
        return frame
    output = frame.copy().sort_values("timestamp").reset_index(drop=True)
    contracts = output["source_contract"].astype(str)
    transitions = output.index[contracts.ne(contracts.shift())].tolist()[1:]
    cumulative = 0.0
    adjustments = pd.Series(0.0, index=output.index)
    # Work backwards so older history receives every later roll gap.
    for idx in reversed(transitions):
        previous_close = float(output.loc[idx - 1, "close"])
        next_open = float(output.loc[idx, "open"])
        cumulative += next_open - previous_close
        adjustments.loc[: idx - 1] = cumulative
    for column in ("open", "high", "low", "close"):
        output[column] = pd.to_numeric(output[column], errors="coerce") + adjustments
    return output


def _empty(*, include_contract: bool = False) -> pd.DataFrame:
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    if include_contract:
        columns.append("source_contract")
    return pd.DataFrame(columns=columns)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _unix_ns(value: datetime) -> int:
    return int(_utc(value).timestamp() * 1_000_000_000)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
