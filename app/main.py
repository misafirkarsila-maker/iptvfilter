"""Xtream Filter — ana uygulama girişi."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
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

MAIN_PANEL_DOMAIN = os.getenv("MAIN_PANEL_DOMAIN", "iptvfilter.online").strip()
API_SERVER_DOMAIN = os.getenv("API_SERVER_DOMAIN", "newlist.best").strip()


@app.middleware("http")
async def enforce_dedicated_api_domain(request: Request, call_next):
    """newlist.best yalnızca TV API & M3U akışlarına hizmet verir.
    Web paneline (giriş, kayıt, yönetim vb.) gelen tarayıcı isteklerini ana panele (iptvfilter.online) yönlendirir.
    """
    host = request.headers.get("host", "").split(":")[0].lower()
    if API_SERVER_DOMAIN and host == API_SERVER_DOMAIN.lower():
        path = request.url.path
        # Web paneline ait sayfalar (yalnızca bunlar ana panele yönlendirilir)
        panel_routes = (
            "/login", "/register", "/logout", "/providers", "/categories",
            "/settings", "/board", "/sync", "/static", "/docs", "/redoc", "/openapi.json"
        )
        is_panel_page = (
            path == "/"
            or path == ""
            or any(path.startswith(p) for p in panel_routes)
            or (path == "/admin" or path.startswith("/admin/users") or path.startswith("/admin/settings"))
        )
        if is_panel_page:
            target_url = f"https://{MAIN_PANEL_DOMAIN}{path}"
            if request.url.query:
                target_url += f"?{request.url.query}"
            return RedirectResponse(target_url, status_code=302)

    return await call_next(request)


# Statik dosyalar
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "app" / "static")), name="static")

# PWA / Favicon Kök Yolları
@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "favicon" / "favicon.ico"), media_type="image/x-icon")

@app.api_route("/site.webmanifest", methods=["GET", "HEAD"], include_in_schema=False)
async def manifest():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "favicon" / "site.webmanifest"), media_type="application/manifest+json")

@app.api_route("/sw.js", methods=["GET", "HEAD"], include_in_schema=False)
async def service_worker():
    return FileResponse(
        str(config.BASE_DIR / "app" / "static" / "sw.js"),
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

# SEO Kök Yolları
@app.api_route("/robots.txt", methods=["GET", "HEAD"], include_in_schema=False)
async def robots():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "robots.txt"), media_type="text/plain")

@app.api_route("/sitemap.xml", methods=["GET", "HEAD"], include_in_schema=False)
async def sitemap():
    return FileResponse(str(config.BASE_DIR / "app" / "static" / "sitemap.xml"), media_type="application/xml")

# Dashboard (web panel)
app.include_router(dashboard_router)

# Kendi Xtream API output
app.include_router(api_output_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
