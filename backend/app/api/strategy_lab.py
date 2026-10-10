from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.api.safe_errors import safe_http_error
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
    research_experiment: dict[str, Any] | None = None


class BacktestRunUpdate(BaseModel):
    name: str | None = None
    notes: str | None = None
    test_role: str | None = None
    tags: list[str] | None = None


class JobSubmission(BaseModel):
    request_key: str = Field(min_length=1, max_length=100)
    runs: list[BacktestRequest] = Field(min_length=1, max_length=100)


class ResearchExperimentRequest(BaseModel):
    base: BacktestRequest
    axes: list[dict[str, Any]] = Field(min_length=1, max_length=2)
    request_key: str = Field(min_length=1, max_length=80)
    name: str = Field(default='', max_length=200)
    notes: str = Field(default='', max_length=10000)
    tags: list[str] = Field(default_factory=list)
    role: str = 'development'
    workers: str | int = 'global'


@router.post('/research-experiments/preview')
def preview_research(payload: ResearchExperimentRequest):
    from app.services.research_experiments import preview
    try:
        return preview(payload.base.model_dump(), payload.axes)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/research-experiments')
def submit_research(payload: ResearchExperimentRequest, services: AppServices = Depends(get_services)):
    from app.services.research_experiments import children
    try:
        plan, runs = children(payload.base.model_dump(), payload.axes, payload.request_key,
                              payload.name, payload.notes, payload.tags, payload.role)
        from app.research_runtime import worker_count
        if payload.workers != 'global':
            worker_count(payload.workers)
        parent = {**payload.base.model_dump(), 'experiment_group': runs[0]['experiment_group'],
                  'run_name': payload.name or 'Research experiment', 'run_notes': payload.notes,
                  'run_tags': payload.tags, 'test_role': payload.role, 'experiment_type': plan['kind'],
                  'research_workers': payload.workers, 'research_plan': plan,
                  'research_base': payload.base.model_dump(), 'research_children': runs}
        return {**plan, 'experiment_group': runs[0]['experiment_group'],
                'jobs': services.backtest_jobs.enqueue([parent], payload.request_key)}
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/futures-preflight')
def futures_preflight(payload: BacktestRequest, services: AppServices = Depends(get_services)):
    from app.services.futures_preflight import preflight
    try:
        return preflight(services.backtest, payload.model_dump())
    except (ValueError, KeyError):
        raise HTTPException(400, 'Unsupported futures symbol, strategy, timeframe, session or date configuration')


@router.get('/jobs')
def jobs(compact: bool = False, services: AppServices = Depends(get_services)):
    return {'jobs': services.backtest_jobs.compact_list() if compact else services.backtest_jobs.list(), 'max_workers': services.backtest_jobs.workers, 'worker_mode': services.backtest_jobs.worker_mode, 'compute': services.backtest_jobs.compute_settings()}


class ComputeSettingsRequest(BaseModel):
    mode: str


@router.get('/compute-settings')
def compute_settings(services: AppServices = Depends(get_services)):
    return services.backtest_jobs.compute_settings()


@router.put('/compute-settings')
def update_compute_settings(payload: ComputeSettingsRequest, services: AppServices = Depends(get_services)):
    try:
        return services.backtest_jobs.set_worker_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/jobs')
def submit_jobs(payload: JobSubmission, services: AppServices = Depends(get_services)):
    try:
        return {'jobs': services.backtest_jobs.enqueue([run.model_dump() for run in payload.runs], payload.request_key)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/jobs/{job_id}/cancel')
def cancel_job(job_id: str, services: AppServices = Depends(get_services)):
    try:
        return services.backtest_jobs.cancel(job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete('/jobs')
def clear_finished_jobs(services: AppServices = Depends(get_services)):
    return services.backtest_jobs.clear_finished()


@router.delete('/jobs/{job_id}')
def delete_job(job_id: str, services: AppServices = Depends(get_services)):
    try:
        return services.backtest_jobs.delete(job_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if message == 'Job not found' else 409, message) from exc


@router.post('/jobs/{job_id}/retry')
def retry_job(job_id: str, request_key: str, services: AppServices = Depends(get_services)):
    try:
        return {'jobs': services.backtest_jobs.retry(job_id, request_key)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/runs")
def backtest_runs(limit: int = Query(default=100, ge=1, le=500), services: AppServices = Depends(get_services)):
    return {"runs": services.backtest.list_runs(limit=limit)}


@router.get("/experiments/{experiment_group}")
def backtest_experiment(experiment_group: str, compact: bool = False, services: AppServices = Depends(get_services)):
    parent = next((j for j in (services.backtest_jobs.compact_list() if compact else services.backtest_jobs.list()) if (j['payload'].get('research_children') or j['payload'].get('research_count')) and j['payload'].get('experiment_group') == experiment_group), None)
    try:
        if compact:
            from app.storage.research_experiment_repository import ResearchExperimentRepository
            from app.services.research_status import experiment_status
            document = ResearchExperimentRepository(services.backtest_jobs.database).get(experiment_group)
            if document:
                document['cells'] = experiment_status(services.backtest_jobs.database, experiment_group)['cells']
                document['performance'] = {k:v for k,v in document.get('performance',{}).items() if k!='cells'}
                return {'experiment_group':experiment_group,'runs':[], 'experiment':document,'parent_job':parent}
        result = services.backtest.get_experiment(experiment_group)
        result['parent_job'] = parent
        return result
    except ValueError as exc:
        if parent:
            return {'experiment_group':experiment_group,'runs':[],'parent_job':parent,
                    'experiment':{'plan':services.backtest_jobs.get(parent['id'])['payload']['research_plan'],'cells':[],'status':parent['status']}}
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get('/research-experiments')
def list_research(compact: bool = False, services: AppServices = Depends(get_services)):
    if compact:
        from app.services.research_status import research_history
        return {'experiments': research_history(services.backtest_jobs.database)}
    from app.storage.research_experiment_repository import ResearchExperimentRepository
    return {'experiments': ResearchExperimentRepository(services.backtest_jobs.database).list()}


@router.get("/runs/{run_id}/trades/{trade_index}/review")
def trade_review(run_id: int, trade_index: int, before: int = Query(50, ge=0, le=500), after: int = Query(20, ge=0, le=200), extended: bool = False, services: AppServices = Depends(get_services)):
    from app.services.trade_review import review_trade
    if trade_index < 0:
        raise HTTPException(400, "Invalid trade index")
    try:
        return review_trade(services.backtest,run_id,trade_index,before,after,extended)
    except ValueError as exc:
        raise HTTPException(404,str(exc)) from exc


@router.get("/runs/{run_id}/sections/{section}")
def backtest_run_section(run_id: int, section: str, services: AppServices = Depends(get_services)):
    from app.performance import Profile
    if section not in {"summary", "trades", "analysis"}:
        raise HTTPException(status_code=400, detail="Unknown run section")
    try:
        if services.backtest.runs is None:
            raise ValueError("Backtest run history is unavailable")
        with Profile() as profile:
            result = services.backtest.runs.get_section(run_id, section)
        result["performance"] = profile.snapshot()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/reproducibility")
def backtest_reproducibility(run_id: int, services: AppServices = Depends(get_services)):
    from app.storage.reproducibility import export_manifest
    try:
        if services.backtest.runs is None:raise ValueError("Backtest run history is unavailable")
        return export_manifest(services.backtest.runs.database,run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,detail=str(exc)) from exc


@router.get("/runs/{run_id}/source-archive")
def backtest_source_archive(run_id: int, services: AppServices = Depends(get_services)):
    from app.storage.strategy_source_archive import export_run
    try:
        if services.backtest.runs is None:raise ValueError("Backtest run history is unavailable")
        return export_run(services.backtest.runs.database,run_id)
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
    from app.storage.research_retention import ResearchRunProtected
    try:
        services.backtest.delete_run(run_id)
        return {"ok": True}
    except ResearchRunProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/strategies")
def strategies(services: AppServices = Depends(get_services)):
    return {"strategies": services.backtest.strategies()}


@router.post('/strategies/refresh')
def refresh_strategies(services: AppServices = Depends(get_services)):
    from app.backtesting.strategies import strategy_registry
    from app.backtesting.strategies._refresh import RefreshBusy
    try:
        result = strategy_registry.refresh()
    except RefreshBusy as exc:
        raise HTTPException(409, str(exc)) from None
    return {**result, 'strategies': services.backtest.strategies()}


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
    frontier: datetime | None = None,
    services: AppServices = Depends(get_services),
):
    try:
        from datetime import date
        return services.backtest.replay_bars(
            symbol=symbol, timeframe=timeframe, session=session,
            replay_date=date.fromisoformat(replay_date),
            replay_end_date=date.fromisoformat(replay_end_date) if replay_end_date else None,
            start_time=start_time, context_bars=context_bars, context_days=context_days, frontier=frontier,
        )
    except ValueError as exc:
        raise safe_http_error(exc, 400) from None
    except RuntimeError as exc:
        raise safe_http_error(exc, 503) from None
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


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
    frontier: datetime | None = None,
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
            start_time=start_time, context_bars=context_bars, context_days=context_days, key=key, params=params, frontier=frontier,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise safe_http_error(exc, 400) from None
    except RuntimeError as exc:
        raise safe_http_error(exc, 503) from None
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


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
        raise safe_http_error(exc, 400) from None
    except RuntimeError as exc:
        raise safe_http_error(exc, 503) from None
    except Exception as exc:
        raise safe_http_error(exc, 502) from None


@router.post("/backtest")
def run_backtest(payload: BacktestRequest, services: AppServices = Depends(get_services)):
    try:
        return services.backtest.run(payload.model_dump())
    except ValueError as exc:
        raise safe_http_error(exc, 400) from None
    except RuntimeError as exc:
        raise safe_http_error(exc, 503, default="strategy_execution") from None
    except Exception as exc:
        raise safe_http_error(exc, 502, default="strategy_execution") from None


@router.get('/experiments/{experiment_group}/status')
def research_progress(experiment_group: str, services: AppServices = Depends(get_services)):
    from app.services.research_status import experiment_status
    status = experiment_status(services.backtest_jobs.database, experiment_group)
    if status is None:
        raise HTTPException(404, 'Research experiment not found')
    return status


@router.get('/market-concepts')
def market_concepts(services: AppServices = Depends(get_services)):
    from app.market_concepts import registry
    strategies=services.backtest.strategies()
    return {'items':[{**item,'used_by':[s['key'] for s in strategies
        if any(c.get('key')==item['key'] for c in s.get('concepts',{}).values())]}
        for item in registry.describe()]}
