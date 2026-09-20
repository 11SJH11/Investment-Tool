from datetime import datetime, timedelta, timezone
import json

import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.data.providers.base import Timeframe
from app.services.chart_data import prepare_chart_bars
from app.services.container import AppServices
from app.data.instruments import virtual_symbol


router = APIRouter(tags=["research"])

class ResearchItemCreate(BaseModel):
    source: str = "manual"
    source_item_id: str = ""
    item_type: str = "note"
    instrument: str = ""
    published_at: str | None = None
    title: str
    summary: str = ""
    direction: str = "neutral"
    confidence: float | None = Field(default=None, ge=0, le=100)
    url: str = ""
    metadata: dict = Field(default_factory=dict)


@router.get("/research/items")
def research_items(
    instrument: str | None = None,
    source: str | None = None,
    item_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    services: AppServices = Depends(get_services),
):
    return {"items": services.research.list_items(instrument=instrument, source=source, item_type=item_type, limit=limit)}


@router.post("/research/items")
def save_research_item(req: ResearchItemCreate, services: AppServices = Depends(get_services)):
    try:
        return services.research.save_item(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/research/items/{item_id}")
def delete_research_item(item_id: int, services: AppServices = Depends(get_services)):
    if not services.research.delete_item(item_id):
        raise HTTPException(status_code=404, detail="Research item not found")
    return {"status": "deleted"}


@router.get("/research/{ticker}")
def research_profile(ticker: str, refresh: bool = False, services: AppServices = Depends(get_services)):
    special = virtual_symbol(ticker)
    if special is not None:
        return {
            "symbol": special,
            "metrics": {},
            "availability": {
                "fundamentals": {"status": "not_applicable", "message": "Company fundamentals are not applicable to this market instrument."},
                "price": {"status": "available" if services.market_data is not None else "unavailable"},
            },
        }
    try:
        return services.research.profile(ticker, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Research fetch failed: {exc}") from exc


@router.get("/research/{ticker}/bars")
def research_bars(
    ticker: str,
    timeframe: Timeframe = "1d",
    lookback_days: int = Query(default=365, ge=1, le=5000),
    refresh: bool = False,
    session: str = Query(default="regular", pattern="^(regular|extended)$"),
    services: AppServices = Depends(get_services),
    end_at: datetime | None = None,
):
    if services.market_data is None:
        raise HTTPException(status_code=503, detail="No market data provider is configured")
    try:
        spec = services.market_data.instrument_info(ticker)
        provider = services.market_data.provider_for(ticker)
        delay = services.market_data.historical_delay_minutes(ticker)
        end = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
        end = min(end, end_at.replace(tzinfo=timezone.utc) if end_at.tzinfo is None else end_at) if end_at else end
        end = services.market_data.latest_available_end(ticker, timeframe, end)
        start = end - timedelta(days=lookback_days)
        # Equities need session-aligned 1h/4h bars from a smaller source cadence.
        # Futures/OANDA providers already expose those native resolutions.
        source_timeframe: Timeframe = "30m" if spec.session_profile == "us_equity" and timeframe in {"1h", "4h"} else timeframe
        frame = services.market_data.get_bars(ticker, source_timeframe, start, end, force_refresh=refresh)
        records, aggregation = prepare_chart_bars(frame, timeframe, session, session_profile=spec.session_profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chart data fetch failed: {exc}") from exc

    if "timestamp" in records.columns:
        records = records.copy()
        records["timestamp"] = records["timestamp"].astype(str)
    return {
        "ticker": spec.ticker,
        "timeframe": timeframe,
        "source_timeframe": source_timeframe,
        "lookback_days": lookback_days,
        "count": len(records),
        "bars": records.to_dict(orient="records"),
        "historical_delay_minutes": delay,
        "provider": getattr(provider, "key", None),
        "feed": getattr(provider, "historical_feed", None),
        "adjustment": getattr(provider, "adjustment", None),
        "session": session if spec.session_profile == "us_equity" else "24h",
        "requested_session": session,
        "session_timezone": "America/New_York",
        "session_profile": spec.session_profile,
        "aggregation": aggregation,
        "instrument": spec.as_dict(),
    }

@router.get("/research/{ticker}/indicator")
def research_indicator(
    ticker: str,
    key: str,
    timeframe: Timeframe = "1d",
    lookback_days: int = Query(default=365, ge=1, le=5000),
    session: str = Query(default="regular", pattern="^(regular|extended)$"),
    length: int | None = Query(default=None, ge=1, le=1000),
    params_json: str | None = Query(default=None),
    services: AppServices = Depends(get_services),
):
    """Calculate a registered indicator from the same routed bars used by Charts."""
    if services.market_data is None:
        raise HTTPException(status_code=503, detail="No market data provider is configured")
    from app.indicators import indicator_registry

    try:
        spec = services.market_data.instrument_info(ticker)
        delay = services.market_data.historical_delay_minutes(ticker)
        end = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
        end = services.market_data.latest_available_end(ticker, timeframe, end)
        start = end - timedelta(days=lookback_days)
        source_timeframe: Timeframe = "30m" if spec.session_profile == "us_equity" and timeframe in {"1h", "4h"} else timeframe
        frame = services.market_data.get_bars(ticker, source_timeframe, start, end)
        records, _ = prepare_chart_bars(frame, timeframe, session, session_profile=spec.session_profile)
        indicator = indicator_registry.create(key)
        params = {}
        if params_json:
            decoded = json.loads(params_json)
            if not isinstance(decoded, dict):
                raise ValueError("params_json must be a JSON object")
            params.update(decoded)
        if length is not None:
            params["length"] = length
        values = indicator.calculate(records, **params)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Indicator calculation failed: {exc}") from exc

    if not hasattr(values, "index"):
        raise HTTPException(status_code=500, detail="Indicator returned an unsupported value")
    series = values.iloc[:, 0] if getattr(values, "ndim", 1) > 1 else values
    output = []
    for index, value in series.items():
        if value is None or pd.isna(value):
            continue
        timestamp = records.iloc[int(index)]["timestamp"] if isinstance(index, int) else records.loc[index, "timestamp"]
        output.append({"timestamp": str(timestamp), "value": float(value)})
    return {
        "ticker": spec.ticker, "key": key, "timeframe": timeframe,
        "session": session if spec.session_profile == "us_equity" else "24h",
        "params": params, "values": output,
    }

class ChartIndicatorRequest(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    params: dict = Field(default_factory=dict)


class ChartBatchRequest(BaseModel):
    timeframe: Timeframe = '1d'
    lookback_days: int = Field(default=365, ge=1, le=5000)
    session: str = Field(default='regular', pattern='^(regular|extended)$')
    refresh: bool = False
    end_at: datetime | None = None
    indicators: list[ChartIndicatorRequest] = Field(default_factory=list, max_length=20)


@router.post('/research/{ticker}/chart-data')
def chart_batch(ticker: str, req: ChartBatchRequest, services: AppServices = Depends(get_services)):
    """One routed bar preparation for the entire chart; individual APIs stay compatible."""
    from app.indicators import indicator_registry
    import math
    try:
        indicators = [(item, indicator_registry.create(item.key)) for item in req.indicators]
    except KeyError:
        raise HTTPException(status_code=400, detail='Unknown chart indicator') from None
    result = research_bars(ticker, req.timeframe, req.lookback_days, req.refresh, req.session, services, req.end_at)
    frame = pd.DataFrame(result['bars'], columns=list(result['bars'][0]) if result['bars'] else ['timestamp','open','high','low','close','volume'])
    frame['timestamp'] = pd.to_datetime(frame['timestamp'], utc=True)
    output = []
    for item, indicator in indicators:
        try:
            values = indicator.calculate(frame.copy(), **item.params)
            values = values.iloc[:,0] if getattr(values,'ndim',1)>1 else values
            points = [{'timestamp':str(frame.loc[index,'timestamp']), 'value':float(value)}
                      for index,value in values.items() if value is not None and pd.notna(value) and math.isfinite(float(value))]
            output.append({'key':item.key,'params':item.params,'values':points})
        except (ValueError,TypeError,KeyError,ZeroDivisionError,IndexError):
            output.append({'key':item.key,'params':item.params,'values':[], 'error':'Indicator unavailable. Check parameters and available history.'})
    return {**result,'indicators':output}
