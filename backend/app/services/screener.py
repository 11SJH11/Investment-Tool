from __future__ import annotations

import json
import zipfile
from collections import defaultdict

from app.data.providers.alpaca import AlpacaProvider
from app.data.providers.sec import SecProvider
from app.storage.screener_repository import ScreenerFilters, ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


class ScreenerService:
    SEC_COMPANYFACTS_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"

    def __init__(
        self,
        repository: ScreenerRepository,
        symbols: SymbolRepository,
        *,
        alpaca: AlpacaProvider | None = None,
        sec: SecProvider | None = None,
    ):
        self.repository = repository
        self.symbols = symbols
        self.alpaca = alpaca
        self.sec = sec

    def screen(self, filters: ScreenerFilters, **kwargs):
        return self.repository.screen(filters, **kwargs)

    def refresh_one_fundamental(self, ticker: str) -> dict:
        if self.sec is None:
            raise RuntimeError("SEC provider is not configured")
        result = self.sec.get_fundamentals(ticker)
        self.repository.upsert_fundamentals([result])
        return result

    def refresh_one_price(self, ticker: str) -> dict:
        if self.alpaca is None:
            raise RuntimeError("Alpaca provider is not configured")
        quote = self.alpaca.get_quote(ticker)
        self.repository.upsert_snapshot(quote.ticker, quote.price, quote.timestamp, f"alpaca-{self.alpaca.live_feed}")
        return {"ticker": quote.ticker, "price": quote.price, "timestamp": quote.timestamp.isoformat()}

    def refresh_price_snapshots(self, *, chunk_size: int = 200, limit: int | None = None) -> dict:
        if self.alpaca is None:
            raise RuntimeError("Alpaca provider is not configured")
        symbols = [item["ticker"] for item in self.symbols.search(limit=500, offset=0)]
        # SymbolRepository intentionally caps search at 500, so read the complete list directly.
        with self.symbols.database.connect() as connection:
            query = "SELECT ticker FROM securities WHERE tradable=1 ORDER BY ticker"
            if limit is not None:
                rows = connection.execute(query + " LIMIT ?", (max(1, limit),)).fetchall()
            else:
                rows = connection.execute(query).fetchall()
            symbols = [row["ticker"] for row in rows]

        stored = 0
        failures = 0
        for start in range(0, len(symbols), max(1, chunk_size)):
            chunk = symbols[start:start + chunk_size]
            try:
                snapshots = self.alpaca.get_latest_bars(chunk)
                stored += self.repository.upsert_snapshots(snapshots, f"alpaca-{self.alpaca.live_feed}")
            except Exception:
                failures += len(chunk)
        return {"requested": len(symbols), "stored": stored, "failed": failures, "feed": self.alpaca.live_feed}

    def refresh_bulk_fundamentals(self, *, max_companies: int | None = None) -> dict:
        if self.sec is None:
            raise RuntimeError("SEC provider is not configured")
        archive_path = self.repository.database.path.parent / "sec" / "companyfacts.zip"
        self.sec.http.download_file(self.SEC_COMPANYFACTS_URL, archive_path, headers=self.sec.headers, timeout_seconds=300)
        cik_to_tickers: dict[str, list[str]] = defaultdict(list)
        for ticker, cik in self.symbols.cik_map().items():
            cik_to_tickers[str(cik).zfill(10)].append(ticker)

        parsed = 0
        matched = 0
        records: list[dict] = []
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                if not name.lower().endswith(".json"):
                    continue
                try:
                    payload = json.loads(archive.read(name))
                except (json.JSONDecodeError, KeyError):
                    continue
                cik = str(payload.get("cik") or "").zfill(10)
                tickers = cik_to_tickers.get(cik)
                if not tickers:
                    continue
                parsed += 1
                for ticker in tickers:
                    records.append(self.sec.normalize_company_facts(ticker, payload))
                    matched += 1
                if max_companies is not None and parsed >= max_companies:
                    break
                if len(records) >= 500:
                    self.repository.upsert_fundamentals(records)
                    records.clear()
        if records:
            self.repository.upsert_fundamentals(records)
        return {"companies_parsed": parsed, "ticker_records": matched, "source": "sec-companyfacts-bulk"}
