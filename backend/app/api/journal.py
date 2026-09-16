from __future__ import annotations

import shutil
from pathlib import Path
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.brokers.base import BrokerHistoryError
from app.core.journal_analytics import journal_zone
from app.services.container import AppServices


router = APIRouter(tags=["journal"])


class ReviewFields(BaseModel):
    playbook_id: int | None = None
    setup_grade: str = ""
    plan_followed: str = ""
    review_data: dict = Field(default_factory=dict)


class TradeCreate(ReviewFields):
    source: str = "live_manual"
    name: str = "Trade"
    account: str = "Main"
    ticker: str
    direction: str = "long"
    opened_at: str | None = None
    closed_at: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: float | None = None
    position_amount: float | None = None
    position_currency: str = "USD"
    stop_loss: float | None = None
    take_profit: float | None = None
    fees: float = 0.0
    result: str | None = None
    pnl_amount: float | None = None
    pnl_pct: float | None = None
    r_multiple: float | None = None
    planned_rr: float | None = None
    pnl_override: float | None = None
    override_reason: str = ""
    trade_type: str = ""
    setup: str = ""
    market_condition: str = ""
    entry_timeframe: str = ""
    timeframe_alignment: str = ""
    dxy: str = ""
    session_time: str = ""
    tf_type: str = ""
    wick: str = ""
    analysis: str = ""
    entry_notes: str = ""
    management: str = ""
    learning: str = ""
    notes: str = ""
    timeframe_notes: dict[str, str] = Field(default_factory=dict)
    external_provider: str = ""
    external_id: str | None = None
    external_order_id: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    imported_at: str | None = None


class TradeUpdate(ReviewFields):
    source: str | None = None
    name: str | None = None
    account: str | None = None
    ticker: str | None = None
    direction: str | None = None
    opened_at: str | None = None
    closed_at: str | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: float | None = None
    position_amount: float | None = None
    position_currency: str = "USD"
    stop_loss: float | None = None
    take_profit: float | None = None
    fees: float | None = None
    result: str | None = None
    pnl_amount: float | None = None
    pnl_pct: float | None = None
    r_multiple: float | None = None
    planned_rr: float | None = None
    pnl_override: float | None = None
    override_reason: str | None = None
    trade_type: str | None = None
    setup: str | None = None
    market_condition: str | None = None
    entry_timeframe: str | None = None
    timeframe_alignment: str | None = None
    dxy: str | None = None
    session_time: str | None = None
    tf_type: str | None = None
    wick: str | None = None
    analysis: str | None = None
    entry_notes: str | None = None
    management: str | None = None
    learning: str | None = None
    notes: str | None = None
    timeframe_notes: dict[str, str] | None = None
    external_provider: str | None = None
    external_id: str | None = None
    external_order_id: str | None = None
    source_metadata: dict | None = None
    imported_at: str | None = None




class JournalReportRequest(BaseModel):
    account: str = ""
    external_account_key: str = ""
    playbook_id: int | None = None
    setup_grade: str = ""
    plan_followed: str = ""
    session_time: str = ""
    timezone: str = ""
    source: str = ""
    ticker: str = ""
    direction: str = ""
    result: str = ""
    setup: str = ""
    entry_timeframe: str = ""
    market_condition: str = ""
    date_from: str = ""
    date_to: str = ""


class DailyReviewRequest(BaseModel):
    review_date: str
    account: str = "Main"
    focus_goal: str = ""
    market_condition: str = ""
    emotional_state: str = ""
    process: str = ""
    pair: str = ""
    session: str = ""
    setups: str = ""
    learnings: str = ""
    psychology: str = ""
    mistakes: str = ""
    did_well: str = ""
    improve: str = ""
    actionable_steps: str = ""
    thoughts: str = ""


class ReviewFieldDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    type: str = Field(default="select", pattern="^(select|multi|text)$")
    options: list[str] = Field(default_factory=list)
    allow_custom: bool = True


class PlaybookRequest(BaseModel):
    sections: dict[str, str] = Field(default_factory=dict)
    review_fields: list[ReviewFieldDefinition] = Field(default_factory=list)
    title: str
    category: str = "Entry Model"
    description: str = ""
    rules: str = ""
    checklist: str = ""
    notes: str = ""


def resolved_filters(req, services):
    try:
        return services.journal_repository.filters(req.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get("/journal/settings")
def journal_settings(services: AppServices = Depends(get_services)):
    return {"timezone": services.database.get_setting("journal_timezone"), "date_basis": "entry"}


class JournalSettingsRequest(BaseModel):
    timezone: str


@router.put("/journal/settings")
def save_journal_settings(req: JournalSettingsRequest, services: AppServices = Depends(get_services)):
    try:
        journal_zone(req.timezone)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    services.database.set_setting("journal_timezone", req.timezone)
    return {"timezone": req.timezone, "date_basis": "entry"}


@router.get("/journal/brokers")
def broker_status(services: AppServices = Depends(get_services)):
    return services.broker_sync.status()


@router.post("/journal/brokers/sync")
def broker_sync(services: AppServices = Depends(get_services)):
    try:
        return services.broker_sync.sync()
    except BrokerHistoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get("/journal/trades")
def list_trades(filters: JournalReportRequest = Depends(), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), services: AppServices = Depends(get_services)):
    rows = services.journal_repository.filtered_trades(resolved_filters(filters, services))
    items = rows[offset:offset + limit]
    for item in items:
        item["attachments"] = _attachments(services, "trade", item["id"])
    return {"items": items, "total": len(rows), "offset": offset, "limit": limit}


@router.get("/journal/options")
def journal_options(services: AppServices = Depends(get_services)):
    rows = services.journal_repository.filtered_trades()
    return {key: sorted({str(t[key]) for t in rows if t.get(key)}) for key in ("source", "account", "ticker", "setup_grade", "market_condition", "session_time", "setup")}


@router.get("/journal/trades/{trade_id}")
def get_trade(trade_id: int, services: AppServices = Depends(get_services)):
    item = services.journal_repository.get_trade(trade_id)
    if not item:
        raise HTTPException(status_code=404, detail="Trade not found")
    item["attachments"] = _attachments(services, "trade", trade_id)
    return item


@router.post("/journal/trades")
def create_trade(req: TradeCreate, services: AppServices = Depends(get_services)):
    try:
        if req.source.startswith("broker_"):
            raise ValueError("Use Sync broker trades to import broker execution facts")
        return services.journal.create_trade(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/journal/trades/{trade_id}")
def update_trade(trade_id: int, req: TradeUpdate, services: AppServices = Depends(get_services)):
    try:
        item = services.journal.update_trade(trade_id, req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    item["attachments"] = _attachments(services, "trade", trade_id)
    return item


@router.delete("/journal/trades/{trade_id}")
def delete_trade(trade_id: int, services: AppServices = Depends(get_services)):
    attachments = services.journal_repository.attachments("trade", trade_id)
    if not services.journal_repository.delete_trade(trade_id):
        raise HTTPException(status_code=404, detail="Trade not found")
    for attachment in attachments:
        _remove_file(services.settings.uploads_dir, attachment["stored_name"])
    return {"status": "deleted"}


@router.get("/journal/analytics")
def analytics(filters: JournalReportRequest = Depends(), services: AppServices = Depends(get_services)):
    return services.journal_repository.analytics(filters=resolved_filters(filters, services))




@router.post("/journal/report")
def journal_report(req: JournalReportRequest, services: AppServices = Depends(get_services)):
    return services.journal_repository.report(resolved_filters(req, services))


@router.get("/journal/calendar")
def calendar(month: str | None = None, filters: JournalReportRequest = Depends(), services: AppServices = Depends(get_services)):
    return {"days": services.journal_repository.calendar(month, filters=resolved_filters(filters, services))}


@router.get("/journal/daily-summary")
def daily_summary(review_date: date, account: str = "Main", timezone: str = "", services: AppServices = Depends(get_services)):
    filters = resolved_filters(JournalReportRequest(timezone=timezone), services)
    result = services.journal_repository.daily(review_date.isoformat(), account, filters)
    if result["review"]:
        result["review"]["attachments"] = _attachments(services, "daily_review", result["review"]["id"])
    return result


@router.get("/journal/daily-reviews")
def daily_reviews(services: AppServices = Depends(get_services)):
    return {"items": services.journal_repository.list_daily_reviews()}


@router.post("/journal/daily-reviews")
def save_daily_review(req: DailyReviewRequest, services: AppServices = Depends(get_services)):
    try:
        date.fromisoformat(req.review_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose a valid review date") from None
    return services.journal_repository.upsert_daily_review(req.model_dump())


@router.get("/journal/playbook")
def playbook(services: AppServices = Depends(get_services)):
    items = services.journal_repository.list_playbook()
    for item in items:
        item["attachments"] = _attachments(services, "playbook", item["id"])
    return {"items": items}


@router.post("/journal/playbook")
def create_playbook(req: PlaybookRequest, services: AppServices = Depends(get_services)):
    validate_playbook(req)
    return services.journal_repository.create_playbook(req.model_dump())


@router.patch("/journal/playbook/{entry_id}")
def update_playbook(entry_id: int, req: PlaybookRequest, services: AppServices = Depends(get_services)):
    validate_playbook(req)
    item = services.journal_repository.update_playbook(entry_id, req.model_dump())
    if item is None:
        raise HTTPException(status_code=404, detail="Playbook entry not found")
    return item


@router.delete("/journal/playbook/{entry_id}")
def delete_playbook(entry_id: int, services: AppServices = Depends(get_services)):
    attachments = services.journal_repository.attachments("playbook", entry_id)
    if not services.journal_repository.delete_playbook(entry_id):
        raise HTTPException(status_code=404, detail="Playbook entry not found")
    for attachment in attachments:
        _remove_file(services.settings.uploads_dir, attachment["stored_name"])
    return {"status": "deleted"}


@router.post("/journal/attachments")
def upload_attachment(
    owner_type: str = Form(...),
    owner_id: int = Form(...),
    slot: str = Form(""),
    caption: str = Form(""),
    file: UploadFile = File(...),
    services: AppServices = Depends(get_services),
):
    if owner_type not in {"trade", "daily_review", "playbook"}:
        raise HTTPException(status_code=400, detail="Invalid attachment owner")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Phase 4 attachments currently accept images only")
    table = {"trade": "journal_trades", "daily_review": "daily_reviews", "playbook": "playbook_entries"}[owner_type]
    with services.database.connect() as connection:
        exists = connection.execute(f"SELECT id FROM {table} WHERE id=?", (owner_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Attachment owner not found")
    suffix = Path(file.filename or "image").suffix.lower()[:10]
    stored_name = f"{uuid4().hex}{suffix}"
    services.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    target = services.settings.uploads_dir / stored_name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    item = services.journal_repository.add_attachment({
        "owner_type": owner_type, "owner_id": owner_id, "slot": slot,
        "original_name": file.filename or stored_name, "stored_name": stored_name,
        "mime_type": file.content_type or "application/octet-stream", "caption": caption,
    })
    return _with_url(item)


@router.get("/journal/attachments/{owner_type}/{owner_id}")
def attachments(owner_type: str, owner_id: int, services: AppServices = Depends(get_services)):
    return {"items": _attachments(services, owner_type, owner_id)}


@router.delete("/journal/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, services: AppServices = Depends(get_services)):
    item = services.journal_repository.delete_attachment(attachment_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    _remove_file(services.settings.uploads_dir, item["stored_name"])
    return {"status": "deleted"}


def _attachments(services: AppServices, owner_type: str, owner_id: int) -> list[dict]:
    return [_with_url(item) for item in services.journal_repository.attachments(owner_type, owner_id)]


def _with_url(item: dict) -> dict:
    return {**item, "url": f"/uploads/{item['stored_name']}"}


def _remove_file(root: Path, name: str) -> None:
    try:
        (root / name).unlink(missing_ok=True)
    except OSError:
        pass


def validate_playbook(req):
    ids = [field.id for field in req.review_fields]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Review fields must have unique stable IDs")
