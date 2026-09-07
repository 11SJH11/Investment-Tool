from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time as _time
from typing import Any

import pandas as pd

from app.data.http import JsonHttpClient
from app.data.providers.base import MarketDataProvider, Quote, Timeframe
from app.data.instruments import normalize_symbol


_TIMEFRAME_MAP: dict[str, str] = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
    "1w": "W",
}

_APPROX_STEP: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(days=7),
}


class OandaProvider(MarketDataProvider):
    key = "oanda"
    cache_namespace = "oanda-mid-v1"
    historical_delay_minutes = 0
    historical_feed = "mid"
    adjustment = None

    def __init__(
        self,
        access_token: str,
        *,
        environment: str = "practice",
        practice_base_url: str = "https://api-fxpractice.oanda.com",
        live_base_url: str = "https://api-fxtrade.oanda.com",
        http: JsonHttpClient | None = None,
    ):
        if not access_token:
            raise ValueError("OANDA access token is required")
        env = str(environment or "practice").strip().lower()
        if env not in {"practice", "live"}:
            raise ValueError("OANDA_ENVIRONMENT must be 'practice' or 'live'")
        self.access_token = access_token
        self.environment = env
        self.base_url = (practice_base_url if env == "practice" else live_base_url).rstrip("/")
        self.http = http or JsonHttpClient()
        self._latest_complete_cache: dict[str, tuple[float, datetime]] = {}

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept-Datetime-Format": "RFC3339",
        }

    @staticmethod
    def provider_symbol(ticker: str) -> str:
        symbol = normalize_symbol(ticker)
        if symbol == "XAUUSD":
            return "XAU_USD"
        if "_" in symbol:
            return symbol
        # Ledger only advertises XAUUSD for OANDA in this phase. Keeping this
        # explicit avoids silently turning arbitrary equity tickers into FX pairs.
        raise ValueError(f"Unsupported OANDA Ledger symbol: {symbol}")


    def latest_available_end(self, ticker: str, timeframe: Timeframe, reference: datetime | None = None) -> datetime:
        """Return an exclusive end timestamp immediately after the newest complete candle.

        OANDA rejects/behaves inconsistently around future/closed-market windows on some
        instruments. Charts, Replay and backtests can use this to clamp requests to the
        newest complete provider candle instead of assuming `now` is tradeable. A short
        cache avoids an extra provider round-trip on every indicator request.
        """
        granularity = _TIMEFRAME_MAP.get(timeframe)
        if granularity is None:
            raise ValueError(f"Unsupported OANDA timeframe: {timeframe}")
        instrument = self.provider_symbol(ticker)
        key = f"{instrument}:{timeframe}"
        now_monotonic = _time.monotonic()
        reference = _utc(reference or datetime.now(timezone.utc))
        cached = self._latest_complete_cache.get(key)
        if cached and now_monotonic - cached[0] < 60:
            return min(reference, cached[1])
        # Ask OANDA for its latest candles without a `to` timestamp. On closed
        # markets (weekends/bank holidays) sending the local wall-clock time can
        # occasionally be rejected as a future timestamp by the practice API.
        # A count-only request always resolves from OANDA's own latest available
        # market time and is therefore the safest freshness probe.
        payload = self.http.get_json(
            f"{self.base_url}/v3/instruments/{instrument}/candles",
            params={
                "price": "M",
                "granularity": granularity,
                "count": 3,
                "smooth": "false",
            },
            headers=self.headers,
        )
        complete = [c for c in (payload.get("candles") or []) if c.get("complete") is not False and c.get("time")]
        if not complete:
            # Fall back conservatively; the normal get_bars request can still decide
            # whether data exists. This keeps a temporary provider quirk from making
            # the whole chart endpoint fail.
            return reference
        latest_start = _to_datetime(complete[-1]["time"])
        provider_latest_end = latest_start + _APPROX_STEP[timeframe]
        # Cache the provider's true latest boundary, not the caller's requested
        # reference. Historical backtests can call this method with an old date;
        # caching that old date would otherwise make a later live chart look stale.
        self._latest_complete_cache[key] = (now_monotonic, provider_latest_end)
        return min(reference, provider_latest_end)

    def get_quote(self, ticker: str) -> Quote:
        now = datetime.now(timezone.utc)
        frame = self.get_bars(ticker, "1m", now - timedelta(days=2), now)
        if frame.empty:
            raise RuntimeError(f"No OANDA candles returned for {ticker}")
        row = frame.iloc[-1]
        return Quote(ticker=normalize_symbol(ticker), price=float(row["close"]), timestamp=_to_datetime(row["timestamp"]))

    def get_bars(self, ticker: str, timeframe: Timeframe, start: datetime, end: datetime) -> pd.DataFrame:
        granularity = _TIMEFRAME_MAP.get(timeframe)
        if granularity is None:
            raise ValueError(f"Unsupported OANDA timeframe: {timeframe}")
        instrument = self.provider_symbol(ticker)
        start = _utc(start)
        end = _utc(end)
        # Clamp every OANDA candle request defensively, not only callers that
        # remembered to probe freshness first. This prevents chart/replay/audit
        # paths from ever sending a future/closed-market `to` timestamp.
        end = min(end, self.latest_available_end(ticker, timeframe, end))
        if start >= end:
            return _empty()

        # OANDA caps one candles response at 5,000. Request conservative chunks
        # so long Replay/backtest ranges paginate deterministically without relying
        # on provider-side truncation behaviour.
        max_span = _APPROX_STEP[timeframe] * 4500
        cursor = start
        rows: list[dict[str, Any]] = []
        while cursor < end:
            chunk_end = min(end, cursor + max_span)
            payload = self.http.get_json(
                f"{self.base_url}/v3/instruments/{instrument}/candles",
                params={
                    "price": "M",
                    "granularity": granularity,
                    "from": _rfc3339(cursor),
                    "to": _rfc3339(chunk_end),
                    "smooth": "false",
                    "includeFirst": "true",
                },
                headers=self.headers,
            )
            candles = payload.get("candles") or []
            for candle in candles:
                midpoint = candle.get("mid") or {}
                if not candle.get("time") or midpoint.get("o") is None:
                    continue
                # An incomplete candle changes underneath the user and is unsafe
                # for deterministic Replay/backtests. Live streaming is a later phase.
                if candle.get("complete") is False:
                    continue
                rows.append(
                    {
                        "timestamp": candle["time"],
                        "open": midpoint.get("o"),
                        "high": midpoint.get("h"),
                        "low": midpoint.get("l"),
                        "close": midpoint.get("c"),
                        "volume": candle.get("volume", 0),
                    }
                )
            if chunk_end >= end:
                break
            # The next chunk intentionally overlaps its boundary; de-duplication
            # below makes this safe and prevents a missing bar at the join.
            cursor = chunk_end

        if not rows:
            return _empty()
        frame = pd.DataFrame(rows)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return (
            frame.dropna(subset=["timestamp", "open", "high", "low", "close"])
            .drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
