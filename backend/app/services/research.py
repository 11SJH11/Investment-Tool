from __future__ import annotations

from app.services.fundamentals import FundamentalsService
from app.services.screener import ScreenerService
from app.storage.research_repository import ResearchRepository
from app.storage.screener_repository import ScreenerRepository
from app.storage.symbol_repository import SymbolRepository


class ResearchService:
    def __init__(
        self,
        symbols: SymbolRepository,
        screener_repository: ScreenerRepository,
        screener: ScreenerService,
        fundamentals: FundamentalsService | None,
        items: ResearchRepository | None = None,
    ):
        self.symbols = symbols
        self.screener_repository = screener_repository
        self.screener = screener
        self.fundamentals = fundamentals
        self.items = items


    def list_items(self, *, instrument: str | None = None, source: str | None = None, item_type: str | None = None, limit: int = 200) -> list[dict]:
        if self.items is None:
            return []
        return self.items.list_items(instrument=instrument, source=source, item_type=item_type, limit=limit)

    def save_item(self, payload: dict) -> dict:
        if self.items is None:
            raise RuntimeError("Research item storage is unavailable")
        return self.items.upsert_item(payload)

    def delete_item(self, item_id: int) -> bool:
        if self.items is None:
            return False
        return self.items.delete_item(item_id)

    def profile(self, ticker: str, *, refresh: bool = False) -> dict:
        ticker = ticker.upper().strip()
        symbol = self.symbols.get(ticker)
        if symbol is None:
            raise KeyError(f"Unknown cached symbol: {ticker}")

        metrics = self.screener_repository.get_metrics(ticker)
        has_fundamentals = bool(metrics and metrics.get("has_fundamentals"))
        fundamental_error: str | None = None

        # A market snapshot row can exist before SEC data does. Treat the two
        # caches independently so opening Research auto-populates missing
        # fundamentals instead of requiring the manual Refresh button.
        should_fetch_fundamentals = refresh or not has_fundamentals
        if should_fetch_fundamentals and self.fundamentals is not None and symbol.get("cik"):
            try:
                fresh = self.fundamentals.get(ticker, refresh=refresh)
                self.screener_repository.upsert_fundamentals([fresh])
                metrics = self.screener_repository.get_metrics(ticker)
                has_fundamentals = bool(metrics and metrics.get("has_fundamentals"))
            except Exception as exc:
                # Research should still show chart/price for ETFs, unusual SEC
                # filers, or temporary SEC failures.
                fundamental_error = str(exc)
                metrics = self.screener_repository.get_metrics(ticker)

        if refresh or metrics is None or metrics.get("price") is None:
            try:
                self.screener.refresh_one_price(ticker)
                metrics = self.screener_repository.get_metrics(ticker) or metrics
            except Exception:
                # A failed live snapshot should not hide cached fundamentals.
                metrics = self.screener_repository.get_metrics(ticker) or metrics

        metrics = metrics or self.screener_repository.get_metrics(ticker) or {}
        has_fundamentals = bool(metrics.get("has_fundamentals"))

        if has_fundamentals:
            fundamental_status = "available"
            fundamental_message = None
        elif fundamental_error:
            fundamental_status = "error"
            fundamental_message = fundamental_error
        elif self.fundamentals is None:
            fundamental_status = "provider_unavailable"
            fundamental_message = "SEC fundamentals provider is not configured."
        elif not symbol.get("cik"):
            fundamental_status = "not_applicable"
            fundamental_message = "No SEC CIK mapping is available for this security."
        else:
            fundamental_status = "unavailable"
            fundamental_message = "No usable SEC fundamental metrics were returned for this security."

        return {
            "symbol": symbol,
            "metrics": metrics,
            "availability": {
                "fundamentals": {
                    "status": fundamental_status,
                    "message": fundamental_message,
                },
                "price": {
                    "status": "available" if metrics.get("price") is not None else "unavailable",
                },
            },
        }
