from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_services
from app.services.container import AppServices
from app.storage.screener_repository import ScreenerFilters


router = APIRouter(tags=["screener"])


@router.get("/screener")
def screen(
    query: str = "",
    exchange: str | None = None,
    security_type: str | None = "stock",
    tradable: bool | None = True,
    fractionable: bool | None = None,
    shortable: bool | None = None,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    min_market_cap: float | None = Query(default=None, ge=0),
    max_market_cap: float | None = Query(default=None, ge=0),
    min_pe: float | None = None,
    max_pe: float | None = None,
    min_revenue_growth: float | None = None,
    min_net_margin: float | None = None,
    min_operating_margin: float | None = None,
    min_roe: float | None = None,
    positive_fcf: bool | None = None,
    require_fundamentals: bool = False,
    sort_by: str = "ticker",
    sort_dir: str = "asc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    services: AppServices = Depends(get_services),
):
    filters = ScreenerFilters(
        query=query, exchange=exchange, security_type=security_type, tradable=tradable, fractionable=fractionable,
        shortable=shortable, min_price=min_price, max_price=max_price,
        min_market_cap=min_market_cap, max_market_cap=max_market_cap,
        min_pe=min_pe, max_pe=max_pe, min_revenue_growth=min_revenue_growth,
        min_net_margin=min_net_margin, min_operating_margin=min_operating_margin,
        min_roe=min_roe, positive_fcf=positive_fcf, require_fundamentals=require_fundamentals,
    )
    total, items = services.screener.screen(
        filters, sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset
    )
    return {"total": total, "items": items, "coverage": services.screener_repository.counts()}


@router.post("/screener/refresh/prices")
def refresh_prices(
    limit: int | None = Query(default=None, ge=1, le=20000),
    services: AppServices = Depends(get_services),
):
    try:
        return services.screener.refresh_price_snapshots(limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Price snapshot refresh failed: {exc}") from exc


@router.post("/screener/refresh/fundamentals")
def refresh_fundamentals(
    max_companies: int | None = Query(default=None, ge=1, le=20000),
    services: AppServices = Depends(get_services),
):
    try:
        return services.screener.refresh_bulk_fundamentals(max_companies=max_companies)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SEC bulk refresh failed: {exc}") from exc


from pydantic import BaseModel, Field
from typing import Literal

class ScanQuery(BaseModel):
    conditions: list[dict] = Field(default_factory=list, max_length=30)
    match: Literal['all','any'] = 'all'
    security_type: str = 'stock'
    text: str = ''
    exchange: str = ''
    tradable: bool | None = True
    fractionable: bool | None = None
    shortable: bool | None = None
    require_fundamentals: bool = False
    limit: int = Field(default=500,ge=1,le=5000)
    offset: int = Field(default=0,ge=0)

@router.post('/screener/query')
def scan_query(req: ScanQuery,services: AppServices=Depends(get_services)):
    try:return services.technical_screener.query(**req.model_dump())
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from None

@router.post('/screener/refresh/technicals')
def refresh_technicals(services: AppServices=Depends(get_services)):
    return services.technical_screener.start()

@router.get('/screener/refresh/technicals')
def technical_status(services: AppServices=Depends(get_services)):
    return services.technical_screener.status()
