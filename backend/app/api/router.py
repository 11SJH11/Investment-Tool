from fastapi import APIRouter

from app.api.data import router as data_router
from app.api.health import router as health_router
from app.api.portfolio import router as portfolio_router
from app.api.journal import router as journal_router
from app.api.research import router as research_router
from app.api.screener import router as screener_router
from app.api.strategy_lab import router as strategy_lab_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(data_router)
api_router.include_router(screener_router)
api_router.include_router(research_router)
api_router.include_router(portfolio_router)
api_router.include_router(journal_router)
api_router.include_router(strategy_lab_router)
