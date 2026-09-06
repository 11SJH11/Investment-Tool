from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_services
from app.services.container import AppServices


router = APIRouter(tags=["portfolio"])


class TransactionRequest(BaseModel):
    account: str = "Main"
    ticker: str
    action: str
    occurred_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    input_mode: str = "amount"
    amount: float | None = None
    quantity: float | None = None
    price_override: float | None = None
    # Backward-compatible Phase 4 field. New UI uses price_override.
    price: float | None = None
    fees: float = 0.0
    base_currency: str = "GBP"
    asset_currency: str = "USD"
    fees_currency: str | None = None
    note: str = ""


@router.get("/portfolio")
def portfolio(account: str | None = None, services: AppServices = Depends(get_services)):
    try:
        return services.portfolio.summary(account)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/portfolio/transactions")
def add_transaction(req: TransactionRequest, services: AppServices = Depends(get_services)):
    try:
        return services.portfolio.add_transaction(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/portfolio/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, services: AppServices = Depends(get_services)):
    try:
        deleted = services.portfolio.delete_transaction(transaction_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Cannot delete transaction: {exc}") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted"}


@router.post("/portfolio/refresh-prices")
def refresh_portfolio_prices(account: str | None = None, services: AppServices = Depends(get_services)):
    return services.portfolio.summary(account, refresh_prices=True)
