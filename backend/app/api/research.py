from datetime import datetime, timedelta, timezone
import json

import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_services
from app.data.providers.base import Timeframe
from app.services.chart_data import prepare_chart_bars
from app.services.container import AppServices


router = APIRouter(tags=["research"])


@router.get("/research/{ticker}")
def research_profile(ticker: str, refresh: bool = False, services: AppServices = Depends(get_services)):
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
):
    if services.market_data is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    delay = max(0, services.settings.alpaca_historical_delay_minutes)
    end = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
    start = end - timedelta(days=lookback_days)

    # Use 30m source bars for session-aligned hourly/4-hour candles. This makes
    # the first regular-session candle start at 09:30 New York time rather than
    # inheriting a provider-specific top-of-hour boundary.
    source_timeframe: Timeframe = "30m" if timeframe in {"1h", "4h"} else timeframe
    try:
        frame = services.market_data.get_bars(ticker, source_timeframe, start, end, force_refresh=refresh)
        records, aggregation = prepare_chart_bars(frame, timeframe, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chart data fetch failed: {exc}") from exc

    if "timestamp" in records.columns:
        records = records.copy()
        records["timestamp"] = records["timestamp"].astype(str)
    provider = services.market_data.provider
    return {
        "ticker": ticker.upper(),
        "timeframe": timeframe,
        "source_timeframe": source_timeframe,
        "lookback_days": lookback_days,
        "count": len(records),
        "bars": records.to_dict(orient="records"),
        "historical_delay_minutes": delay,
        "feed": getattr(provider, "historical_feed", None),
        "adjustment": getattr(provider, "adjustment", None),
        "session": session,
        "session_timezone": "America/New_York",
        "aggregation": aggregation,
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
    """Calculate a registered indicator from the same market bars used by Research.

    Keeping this calculation on the backend means chart overlays and strategy plugins
    share one implementation instead of drifting into separate JS/Python formulas.
    """
    if services.market_data is None:
        raise HTTPException(status_code=503, detail="Alpaca market data is not configured")
    from app.indicators import indicator_registry

    delay = max(0, services.settings.alpaca_historical_delay_minutes)
    end = datetime.now(timezone.utc) - timedelta(minutes=delay + (1 if delay else 0))
    start = end - timedelta(days=lookback_days)
    source_timeframe: Timeframe = "30m" if timeframe in {"1h", "4h"} else timeframe
    try:
        frame = services.market_data.get_bars(ticker, source_timeframe, start, end)
        records, _ = prepare_chart_bars(frame, timeframe, session)
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
        "ticker": ticker.upper(), "key": key, "timeframe": timeframe,
        "session": session, "params": params, "values": output,
    }
