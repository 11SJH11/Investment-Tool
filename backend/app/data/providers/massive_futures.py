from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import pandas as pd

from app.data.http import JsonHttpClient
from app.data.contract_reference_cache import ContractReferenceCache
from app.data.continuous_schedule import VERSION, choose_roll, adjust_continuous
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
        reference_cache_path=None,
        roll_policy=VERSION,
    ):
        if not api_key:
            raise ValueError("Massive API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.back_adjust = bool(back_adjust)
        self.http = http or JsonHttpClient()
        self.reference_cache = ContractReferenceCache(reference_cache_path)
        if roll_policy not in {VERSION, 'calendar-front-v1'}:
            raise ValueError('Unknown futures roll schedule version')
        self.roll_policy = roll_policy
        adjustment = "back-adjusted" if self.back_adjust else "unadjusted"
        # Calendar roll is intentionally named in the namespace so a later
        # volume-derived roll policy cannot accidentally reuse incompatible cache.
        self.cache_namespace = f"massive-futures-{roll_policy}-{adjustment}-provenance-v3"
        self.adjustment = adjustment

    def raw_execution_provider(self):
        from copy import copy
        provider = copy(self)
        provider.back_adjust = False
        provider.adjustment = 'unadjusted'
        provider.cache_namespace = self.cache_namespace.replace('back-adjusted', 'unadjusted')
        return provider

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
            if self.roll_policy == 'calendar-front-v1':
                frame = self._continuous_front(spec.root or "", resolution, start, end)
                frame = _back_adjust(frame) if self.back_adjust else frame
            else:
                frame, rolls = self._scheduled_front(spec.root, resolution, start, end)
                frame = adjust_continuous(frame, rolls) if self.back_adjust else frame
            frame['continuous_alias'] = symbol
            frame['provider'] = self.key
            frame['adjustment_mode'] = 'back_adjusted' if self.back_adjust else 'raw'
            return frame
        return self._contract_bars(symbol, resolution, start, end, source_contract=symbol)

    def list_contracts(self, product_code: str, *, refresh: bool = False) -> list[FutureContract]:
        root = str(product_code or "").strip().upper()
        if not root.isalnum() or len(root) > 8:
            raise ValueError("Futures product code is invalid")
        def load():
            return [dict(ticker=c.ticker, product_code=c.product_code,
                         first_trade_date=c.first_trade_date.isoformat(), last_trade_date=c.last_trade_date.isoformat())
                    for c in self._fetch_contracts(root)]
        rows = self.reference_cache.get(self.base_url + ":contracts-v1:" + root, load, refresh=refresh)
        return [FutureContract(c["ticker"], c["product_code"], date.fromisoformat(c["first_trade_date"]),
                               date.fromisoformat(c["last_trade_date"])) for c in rows]

    def _fetch_contracts(self, product_code: str) -> list[FutureContract]:
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
        visited = set()
        while url:
            parts = urlsplit(url)
            base = urlsplit(self.base_url)
            if (parts.scheme, parts.netloc, parts.path) != (base.scheme, base.netloc, "/futures/v1/contracts") or parts.fragment or parts.username or parts.password:
                raise ValueError("Massive contract pagination left the allowed endpoint")
            if url in visited or len(visited) >= 100:
                raise ValueError("Massive contract pagination did not advance or exceeded 100 pages")
            visited.add(url)
            payload = self.http.get_json(url, params=params, headers=headers)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                raise ValueError("Massive contract metadata response is incomplete")
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

    def _segment_bars(self, ticker, resolution, start, end):
        if hasattr(self,'contract_loader'):
            timeframe = next(k for k,v in _RESOLUTION_MAP.items() if v == resolution)
            return self.contract_loader(ticker,timeframe,start,end).copy()
        return self._contract_bars(ticker,resolution,start,end,source_contract=ticker)

    def _scheduled_front(self, root, resolution, start, end):
        contracts = self.list_contracts(root)
        if not contracts:
            raise ValueError(f'No dated contracts available for {root}')
        now = datetime.now(timezone.utc)
        rolls = []
        boundaries = {}
        for old, new in zip(contracts, contracts[1:]):
            if old.last_trade_date < start.date()-timedelta(days=60) or old.last_trade_date > end.date()+timedelta(days=45):
                continue
            begin = datetime.combine(max(old.first_trade_date, new.first_trade_date,
                old.last_trade_date-timedelta(days=46)), time.min, timezone.utc)
            finish = min(now, datetime.combine(old.last_trade_date+timedelta(days=2),time.min,timezone.utc))
            def load(old=old,new=new,begin=begin,finish=finish):
                if begin >= finish:
                    return choose_roll(old,new,_empty(),_empty())
                a = self._contract_bars(old.ticker,'1session',begin,finish,source_contract=old.ticker)
                b = self._contract_bars(new.ticker,'1session',begin,finish,source_contract=new.ticker)
                return choose_roll(old,new,a,b)
            # Fixed pair/date key, shared across all chart resolutions and ranges.
            horizon = 'final' if old.last_trade_date < now.date()-timedelta(days=2) else now.strftime('%Y-%m-%d-%H')
            key = f'{self.base_url}:roll:{VERSION}:{old}:{new}:{horizon}'
            roll = self.reference_cache.get(key,load,refresh=getattr(self,'refresh_schedule',False))
            boundaries[old.ticker] = roll
            rolls.append(roll)
        if any(pd.Timestamp(a['effective_at']) >= pd.Timestamp(b['effective_at']) for a,b in zip(rolls,rolls[1:])):
            raise ValueError('Continuous roll evidence is not chronological; refusing overlapping source contracts')
        segments = []
        for i, contract in enumerate(contracts):
            prior = contracts[i-1] if i else None
            prior_roll = boundaries.get(prior.ticker) if prior else None
            effective = (pd.Timestamp(prior_roll['effective_at']) if prior_roll else
                pd.Timestamp(datetime.combine(prior.last_trade_date+timedelta(days=1) if prior else contract.first_trade_date,time.min,timezone.utc)))
            ending = boundaries.get(contract.ticker)
            until = pd.Timestamp(ending['effective_at']) if ending else pd.Timestamp(datetime.combine(contract.last_trade_date+timedelta(days=1),time.min,timezone.utc))
            lo, hi = max(pd.Timestamp(start),effective,pd.Timestamp(datetime.combine(contract.first_trade_date,time.min,timezone.utc))),min(pd.Timestamp(end),until)
            if lo >= hi:
                continue
            frame = self._segment_bars(contract.ticker,resolution,lo.to_pydatetime(),hi.to_pydatetime())
            frame['roll_method'] = prior_roll['method'] if prior_roll else 'initial-contract'
            frame['roll_schedule_version'] = VERSION
            frame['roll_effective_at'] = effective.isoformat()
            frame['contract_last_trade_date'] = contract.last_trade_date.isoformat()
            segments.append(frame)
        if not segments:
            return _empty(include_contract=True),rolls
        return pd.concat(segments,ignore_index=True).sort_values('timestamp').reset_index(drop=True),rolls

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
        # Uses UTC date boundaries, not exchange expiry instants. No volume/OI
        # crossover or TradingView equivalence is asserted.
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
            frame = self._segment_bars(contract.ticker, resolution, segment_start, segment_end)
            if not frame.empty:
                prior = [c for c in contracts if c.last_trade_date < contract.last_trade_date]
                effective = max(datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc),
                    datetime.combine(prior[-1].last_trade_date + timedelta(days=1), time.min, tzinfo=timezone.utc)) if prior else datetime.combine(contract.first_trade_date, time.min, tzinfo=timezone.utc)
                frame["roll_method"] = "calendar-front"
                frame["roll_schedule_version"] = "calendar-front-v1"
                frame["contract_last_trade_date"] = contract.last_trade_date.isoformat()
                frame["roll_effective_at"] = effective.isoformat()
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
        visited = set()
        while url:
            parts, base = urlsplit(url), urlsplit(self.base_url)
            if (parts.scheme,parts.netloc,parts.path) != (base.scheme,base.netloc,f'/futures/v1/aggs/{ticker}') or parts.fragment or parts.username or parts.password:
                raise ValueError('Massive aggregate pagination left the allowed endpoint')
            if url in visited or len(visited) >= 1000:
                raise ValueError('Massive aggregate pagination did not advance or exceeded its bound')
            visited.add(url)
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
                "session_end_date": [item.get('session_end_date') for item in rows],
            }
        )
        frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["timestamp"], errors="coerce"), unit="ns", utc=True)
        frame["roll_method"] = "dated-contract"
        frame["roll_schedule_version"] = "none"
        frame["contract_last_trade_date"] = ""
        frame["roll_effective_at"] = ""
        frame["adjustment_method"] = "none"
        frame["price_adjustment"] = 0.0
        frame['provider'] = self.key
        frame['adjustment_mode'] = 'raw'
        frame['continuous_alias'] = ''
        frame = frame.loc[(frame.timestamp >= pd.Timestamp(start)) & (frame.timestamp < pd.Timestamp(end))]
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
    output["adjustment_method"] = "backward-additive-observed-gap-v1"
    output["price_adjustment"] = adjustments
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
