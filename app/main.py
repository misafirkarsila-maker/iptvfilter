"""Xtream Filter — ana uygulama girişi."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, crypto_util, settings_manager
from .api_output import router as api_output_router
from .dashboard import router as dashboard_router
from .database import init_db
from .scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uygulama başlarken: Veritabanı, şifreleme ve ayarları başlat
    init_db()
    settings_manager.init_security_settings()
    crypto_util.init_encryption_key()
    config.reload_security_config()
    start_scheduler()
    logging.info("Xtream Filter başlatıldı. API Kullanıcı: %s", config.API_USERNAME)
    yield
    # Kapanırken
    stop_scheduler()


app = FastAPI(title="Xtream Filter", lifespan=lifespan)

# Statik
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "app" / "static")), name="static")

# Dashboard (web panel)
app.include_router(dashboard_router)

# Kendi Xtream API output
app.include_router(api_output_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
