from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.services.container import AppServices

router = APIRouter(prefix="/strategy-lab", tags=["strategy-lab"])


class EntryWindowRequest(BaseModel):
    start: str
    end: str


class BacktestRequest(BaseModel):
    strategy_key: str
    symbols: list[str] | str
    start_date: str
    end_date: str
    primary_timeframe: str = "5m"
    additional_timeframes: list[str] = Field(default_factory=list)
    session: str = "regular"
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    starting_balance: float = 10_000.0
    sizing_mode: str = "risk_pct"
    risk_value: float = 1.0
    commission_per_order: float = 0.0
    slippage_bps: float = 0.0
    spread_bps: float = 0.0
    max_leverage: float = 1.0
    max_open_positions: int = 5
    same_bar_policy: str = "stop_first"
    entry_windows: list[EntryWindowRequest] = Field(default_factory=list)
    trading_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    allow_overnight: bool = True
    force_close_time: str | None = None
    max_trades_per_day: int | None = None
    max_daily_loss_r: float | None = None
    max_consecutive_losses: int | None = None
    cooldown_minutes: int = 0
    save_run: bool = True
    run_name: str = ""
    run_notes: str = ""
    test_role: str = "development"
    experiment_group: str = ""
    run_tags: list[str] = Field(default_factory=list)


class BacktestRunUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    test_role: str | None = None
    tags: list[str] | None = None


@router.get("/runs")
def backtest_runs(limit: int = Query(default=100, ge=1, le=500), services: AppServices = Depends(get_services)):
    return {"runs": services.backtest.list_runs(limit=limit)}


@router.get("/experiments/{experiment_group}")
def backtest_experiment(experiment_group: str, services: AppServices = Depends(get_services)):
    try:
        return services.backtest.get_experiment(experiment_group)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}")
def backtest_run(run_id: int, services: AppServices = Depends(get_services)):
    try:
        return services.backtest.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/runs/{run_id}")
def update_backtest_run(run_id: int, payload: BacktestRunUpdate, services: AppServices = Depends(get_services)):
    try:
        return services.backtest.update_run(run_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/runs/{run_id}")
def delete_backtest_run(run_id: int, services: AppServices = Depends(get_services)):
    try:
        services.backtest.delete_run(run_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/strategies")
def strategies(services: AppServices = Depends(get_services)):
    return {"strategies": services.backtest.strategies()}


@router.get("/indicators")
def indicators(services: AppServices = Depends(get_services)):
    return {"indicators": services.backtest.indicators()}


@router.get("/replay/bars")
def replay_bars(
    symbol: str,
    replay_date: str,
    replay_end_date: str | None = None,
    start_time: str = "09:30",
    timeframe: str = "5m",
    session: str = Query(default="regular", pattern="^(regular|extended|24h)$"),
    context_bars: int = Query(default=100, ge=0, le=50_000),
    context_days: int | None = Query(default=None, ge=1, le=365),
    services: AppServices = Depends(get_services),
):
    try:
        from datetime import date
        return services.backtest.replay_bars(
            symbol=symbol, timeframe=timeframe, session=session,
            replay_date=date.fromisoformat(replay_date),
            replay_end_date=date.fromisoformat(replay_end_date) if replay_end_date else None,
            start_time=start_time, context_bars=context_bars, context_days=context_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Replay data fetch failed: {exc}") from exc


@router.get("/replay/indicator")
def replay_indicator(
    symbol: str,
    replay_date: str,
    key: str,
    replay_end_date: str | None = None,
    start_time: str = "09:30",
    timeframe: str = "5m",
    session: str = Query(default="regular", pattern="^(regular|extended|24h)$"),
    context_bars: int = Query(default=100, ge=0, le=50_000),
    context_days: int | None = Query(default=None, ge=1, le=365),
    params_json: str = "{}",
    services: AppServices = Depends(get_services),
):
    try:
        from datetime import date
        params = json.loads(params_json or "{}")
        if not isinstance(params, dict):
            raise ValueError("params_json must encode an object")
        return services.backtest.replay_indicator(
            symbol=symbol, timeframe=timeframe, session=session, replay_date=date.fromisoformat(replay_date),
            replay_end_date=date.fromisoformat(replay_end_date) if replay_end_date else None,
            start_time=start_time, context_bars=context_bars, context_days=context_days, key=key, params=params,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Replay indicator failed: {exc}") from exc


@router.get("/audit-bars")
def audit_bars(
    symbol: str,
    timeframe: str = "5m",
    session: str = Query(default="regular", pattern="^(regular|extended|24h)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    entry: datetime | None = None,
    exit: datetime | None = None,
    before_bars: int = Query(default=50, ge=0, le=500),
    after_bars: int = Query(default=20, ge=0, le=200),
    services: AppServices = Depends(get_services),
):
    try:
        return services.backtest.audit_bars(
            symbol=symbol, timeframe=timeframe, session=session, start=start, end=end,
            entry=entry, exit=exit, before_bars=before_bars, after_bars=after_bars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Trade audit fetch failed: {exc}") from exc


@router.post("/backtest")
def run_backtest(payload: BacktestRequest, services: AppServices = Depends(get_services)):
    try:
        return services.backtest.run(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Backtest failed: {exc}") from exc
