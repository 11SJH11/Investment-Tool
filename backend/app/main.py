from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.services.container import build_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = build_services(get_settings())
    app.state.services = services
    services.broker_scheduler.start()
    # Keep discovery snapshots warm without blocking startup or discarding stale cache.
    services.technical_screener.ensure_fresh()
    try:
        yield
    finally:
        services.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")
app.include_router(api_router, prefix=settings.api_prefix)
