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
    try:
        from .database import SessionLocal
        from .category_grouper import backfill_category_parents
        with SessionLocal() as db:
            backfill_category_parents(db)
    except Exception as exc:
        logging.warning("Kategori üst başlık güncelleme hatası: %s", exc)
    start_scheduler()
    logging.info("Xtream Filter başlatıldı. API Kullanıcı: %s", config.API_USERNAME)
    yield
    # Kapanırken
    stop_scheduler()


app = FastAPI(title="Xtream Filter", lifespan=lifespan)

from fastapi.responses import FileResponse

# Statik
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "app" / "static")), name="static")

# PWA / Favicon Kök Yolları
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "favicon" / "favicon.ico"), media_type="image/x-icon")

@app.get("/site.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "favicon" / "site.webmanifest"), media_type="application/manifest+json")

@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        str(config.BASE_DIR / "app" / "static" / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

# Dashboard (web panel)
app.include_router(dashboard_router)

# Kendi Xtream API output
app.include_router(api_output_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
