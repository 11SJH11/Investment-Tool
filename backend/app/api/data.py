from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_services
from app.data.providers.base import Timeframe
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
        raise HTTPException(status_code=502, detail=f"Symbol refresh failed: {exc}") from exc


@router.get("/symbols")
def symbols(
    query: str = "",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    services: AppServices = Depends(get_services),
):
    return {
        "total": services.symbols.count(),
        "items": services.symbols.search(query=query, limit=limit, offset=offset),
    }


@router.get("/symbols/{ticker}")
def symbol(ticker: str, services: AppServices = Depends(get_services)):
    item = services.symbols.get(ticker)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Unknown cached symbol: {ticker.upper()}")
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
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    try:
        frame = services.market_data.get_bars(ticker, timeframe, start, end, force_refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Market data fetch failed: {exc}") from exc

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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SEC fundamentals fetch failed: {exc}") from exc


@router.get("/macro/snapshot")
def macro_snapshot(refresh: bool = False, services: AppServices = Depends(get_services)):
    if services.macro is None:
        raise HTTPException(status_code=503, detail="FRED is not configured")
    try:
        return services.macro.get_snapshot(refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FRED fetch failed: {exc}") from exc
