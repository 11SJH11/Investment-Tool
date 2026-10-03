from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.api.safe_errors import safe_http_error
from app.data.providers.base import Timeframe
from app.data.instruments import normalize_symbol, virtual_symbol, virtual_symbols
from app.services.container import AppServices


router = APIRouter(tags=["data"])


@router.get("/data/status")
def data_status(services: AppServices = Depends(get_services)):
    return {
        "providers": services.provider_status(),
        "symbols_cached": services.symbols.count(),
        "configured_provider_kinds": services.providers.configured(),
        "screener_coverage": services.screener_repository.counts(),
    }


@router.get("/data/providers/autochartist/capabilities")
def autochartist_capabilities(services: AppServices = Depends(get_services)):
    return services.autochartist.capability_report()


@router.post("/data/symbols/refresh")
def refresh_symbols(services: AppServices = Depends(get_services)):
    if services.symbol_universe is None:
        raise HTTPException(
            status_code=503,
            detail="No security-master provider configured. Add Alpaca keys or SEC_USER_AGENT to .env.",
        )
    try:
        return services.symbol_universe.refresh()
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


@router.get("/symbols")
def symbols(
    query: str = "",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    services: AppServices = Depends(get_services),
):
    # XAUUSD/NQ1! are provider-routed Ledger aliases rather than Alpaca security-
    # master rows. Surface them in the same search control without polluting the
    # equity refresh table (which intentionally mirrors Alpaca/SEC).
    specials = virtual_symbols(query) if offset == 0 else []
    database_limit = max(0, limit - len(specials))
    database_items = services.symbols.search(query=query, limit=max(1, database_limit), offset=offset) if database_limit else []
    merged = []
    seen = set()
    for item in [*specials, *database_items]:
        ticker = str(item.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            merged.append(item); seen.add(ticker)
        if len(merged) >= limit:
            break
    return {
        "total": services.symbols.count() + len(virtual_symbols()),
        "items": merged,
    }


@router.get("/symbols/{ticker}")
def symbol(ticker: str, services: AppServices = Depends(get_services)):
    item = virtual_symbol(ticker) or services.symbols.get(normalize_symbol(ticker))
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown cached symbol: {normalize_symbol(ticker)}")
    return item


@router.get("/market/bars")
def market_bars(
    ticker: str,
    timeframe: Timeframe = "1d",
    start: datetime = Query(...),
    end: datetime = Query(...),
    refresh: bool = False,
    services: AppServices = Depends(get_services),
):
    if services.market_data is None:
        raise HTTPException(status_code=503, detail="No market data provider is configured")
    try:
        frame = services.market_data.get_bars(ticker, timeframe, start, end, force_refresh=refresh)
    except ValueError as exc:
        raise safe_http_error(exc, 400) from None
    except Exception as exc:
        raise safe_http_error(exc, 502) from None

    records = frame.copy()
    if "timestamp" in records.columns:
        records["timestamp"] = records["timestamp"].astype(str)
    return {
        "ticker": ticker.upper(),
        "timeframe": timeframe,
        "count": len(records),
        "bars": records.to_dict(orient="records"),
    }


@router.get("/fundamentals/{ticker}")
def fundamentals(ticker: str, refresh: bool = False, services: AppServices = Depends(get_services)):
    if services.fundamentals is None:
        raise HTTPException(status_code=503, detail="SEC fundamentals are not configured; set SEC_USER_AGENT")
    try:
        return services.fundamentals.get(ticker, refresh=refresh)
    except KeyError as exc:
        raise safe_http_error(exc, 404) from None
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


@router.get("/macro/snapshot")
def macro_snapshot(refresh: bool = False, services: AppServices = Depends(get_services)):
    if services.macro is None:
        raise HTTPException(status_code=503, detail="FRED is not configured")
    try:
        return services.macro.get_snapshot(refresh=refresh)
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


@router.get("/data/cache")
def cache_diagnostics(services: AppServices = Depends(get_services)):
    """Read-only coverage metadata. Never includes settings, secrets or cache payloads."""
    with services.database.connect() as con:
        rows=[dict(row) for row in con.execute("SELECT ticker,timeframe AS source_timeframe,namespace AS provider_cache,covered_start,covered_end,updated_at FROM market_cache_coverage ORDER BY updated_at DESC,ticker LIMIT 500")]
    return {"items":rows,"limit":500,"note":"Coverage is the requested source range, including possible empty market sessions; it is not proof of uninterrupted bars. Refresh a chart to request newer history. Futures source contracts remain attached to each bar."}


class CacheWarmRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=50)
    timeframe: Timeframe = "1m"
    lookback_days: int = Field(default=30, ge=1, le=3650)
    refresh: bool = False


@router.post("/data/cache/warm")
def warm_market_cache(payload: CacheWarmRequest, services: AppServices = Depends(get_services)):
    if services.market_warmup is None:
        raise HTTPException(503, "No market data provider is configured")
    try:
        return services.market_warmup.start(payload.symbols,timeframe=payload.timeframe,lookback_days=payload.lookback_days,refresh=payload.refresh)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400 if isinstance(exc,ValueError) else 503,str(exc)) from exc


@router.get("/data/cache/warm/{job_id}")
def market_cache_warm_status(job_id: str, services: AppServices = Depends(get_services)):
    if services.market_warmup is None:
        raise HTTPException(503, "No market data provider is configured")
    try:
        return services.market_warmup.get(job_id)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.get("/data/cache/warm")
def market_cache_warm_jobs(services: AppServices = Depends(get_services)):
    return {"items": services.market_warmup.list() if services.market_warmup else []}


@router.post("/data/cache/warm/{job_id}/{action}")
def control_market_cache_warm(job_id: str, action: str, services: AppServices = Depends(get_services)):
    if services.market_warmup is None:
        raise HTTPException(503, "No market data provider is configured")
    if action not in {'pause', 'resume'}:
        raise HTTPException(404, "Unknown cache action")
    try:
        return getattr(services.market_warmup, action)(job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
