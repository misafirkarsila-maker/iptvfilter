"""Dashboard (web paneli) — sağlayıcı yönetimi ve kategori filtreleme."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import config, crypto_util, settings_manager
from .category_grouper import build_category_groups, detect_category_group
from .database import get_db
from .models import Category, Provider, Stream
from .scheduler import run_sync_all
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory=str(config.BASE_DIR / "app" / "templates"))
templates.env.globals["build_category_groups"] = build_category_groups
templates.env.globals["detect_category_group"] = detect_category_group

def _panel_token() -> str:
    pwd = settings_manager.get_panel_password()
    if not pwd:
        return ""
    return hashlib.sha256(pwd.encode()).hexdigest()

def _check_panel_auth(request: Request) -> bool:
    if not settings_manager.has_panel_password():
        return True
    cookie = request.cookies.get("panel_token")
    return cookie == _panel_token()

def _sort_cats(db: Session, provider_id: int):
    return db.query(Category).filter(
        Category.provider_id == provider_id
    ).order_by(Category.content_type, Category.sort_order, Category.name).all()

# ===================== İLK KURULUM SİHİRBAZI =====================

@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if settings_manager.is_setup_completed():
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "api_user": settings_manager.get_api_username(),
            "api_password": settings_manager.get_api_password(),
            "error": None,
        }
    )

@router.post("/setup")
async def setup_submit(
    request: Request,
    auth_mode: str = Form("password"),
    password: Optional[str] = Form(None),
    password_confirm: Optional[str] = Form(None),
):
    if settings_manager.is_setup_completed():
        return RedirectResponse("/", status_code=303)

    if auth_mode == "password":
        pwd = (password or "").strip()
        pwd_confirm = (password_confirm or "").strip()
        if not pwd or len(pwd) < 3:
            return templates.TemplateResponse(
                request,
                "setup.html",
                {
                    "api_user": settings_manager.get_api_username(),
                    "api_password": settings_manager.get_api_password(),
                    "error": "Lütfen en az 3 karakterli bir şifre giriniz.",
                },
                status_code=400,
            )
        if pwd != pwd_confirm:
            return templates.TemplateResponse(
                request,
                "setup.html",
                {
                    "api_user": settings_manager.get_api_username(),
                    "api_password": settings_manager.get_api_password(),
                    "error": "Girdiğiniz şifreler eşleşmiyor.",
                },
                status_code=400,
            )
        settings_manager.complete_setup(pwd)
        config.reload_security_config()
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("panel_token", _panel_token(), httponly=True, max_age=60*60*24*30)
        return resp
    else:
        # Şifresiz kullanım
        settings_manager.complete_setup(None)
        config.reload_security_config()
        return RedirectResponse("/", status_code=303)

# ===================== DASHBOARD / ANA SAYFA =====================

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    # PANEL_PASSWORD tanımlı ise giriş zorunlu, boş ise direkt şifresiz açılır
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)

    providers = db.query(Provider).order_by(Provider.priority.asc(), Provider.id.asc()).all()
    server_host = request.headers.get("host", f"localhost:{config.APP_PORT}")
    active_count = sum(1 for p in providers if p.enabled and p.last_sync_status == "ok")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "providers": providers,
            "req": request,
            "api_user": settings_manager.get_api_username(),
            "api_password": settings_manager.get_api_password(),
            "has_panel_password": settings_manager.has_panel_password(),
            "stream_proxy_enabled": settings_manager.is_stream_proxy_enabled(),
            "server_host": server_host,
            "active_count": active_count,
        }
    )

# ===================== GİRİŞ / ÇIKIŞ =====================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not settings_manager.has_panel_password() or _check_panel_auth(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})

@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    active_pass = settings_manager.get_panel_password()
    if not active_pass or password == active_pass:
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("panel_token", _panel_token(), httponly=True, max_age=60*60*24*30)
        return resp
    return templates.TemplateResponse(
        request, "login.html", {"error": "Yanlış şifre. Lütfen tekrar deneyin."}, status_code=401
    )

@router.post("/logout")
async def logout():
    resp = RedirectResponse("/login" if settings_manager.has_panel_password() else "/", status_code=303)
    resp.delete_cookie("panel_token")
    return resp

# ===================== AYARLAR GÜNCELLEME =====================

@router.post("/settings/panel-password")
async def update_panel_password_endpoint(
    request: Request,
    action_type: str = Form(...),
    new_password: Optional[str] = Form(None),
    new_password_confirm: Optional[str] = Form(None),
):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)

    if action_type == "remove":
        settings_manager.set_panel_password(None)
        config.reload_security_config()
        resp = RedirectResponse("/?msg=panel_pass_removed", status_code=303)
        resp.delete_cookie("panel_token")
        return resp
    else:
        pwd = (new_password or "").strip()
        pwd_confirm = (new_password_confirm or "").strip()
        if not pwd or len(pwd) < 3 or pwd != pwd_confirm:
            return RedirectResponse("/?err=pass_mismatch", status_code=303)
        settings_manager.set_panel_password(pwd)
        config.reload_security_config()
        resp = RedirectResponse("/?msg=panel_pass_updated", status_code=303)
        resp.set_cookie("panel_token", _panel_token(), httponly=True, max_age=60*60*24*30)
        return resp

@router.post("/settings/regenerate-api-password")
async def regenerate_api_password_endpoint(request: Request):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)
    settings_manager.regenerate_api_password()
    config.reload_security_config()
    return RedirectResponse("/?msg=api_pass_regenerated", status_code=303)

@router.post("/settings/custom-api-password")
async def custom_api_password_endpoint(request: Request, api_password: str = Form(...)):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)
    pwd = api_password.strip()
    if not pwd:
        return RedirectResponse("/?err=empty_api_pass", status_code=303)
    settings_manager.set_api_password(pwd)
    config.reload_security_config()
    return RedirectResponse("/?msg=api_pass_updated", status_code=303)

@router.post("/settings/proxy/toggle")
async def toggle_stream_proxy_endpoint(request: Request, enabled: Optional[bool] = Form(None)):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        raise HTTPException(401, "Yetkisiz erişim")
    if enabled is None:
        new_state = not settings_manager.is_stream_proxy_enabled()
    else:
        new_state = bool(enabled)
    settings_manager.set_stream_proxy_enabled(new_state)
    return {"status": "ok", "stream_proxy_enabled": new_state}

# ===================== SAĞLAYICI YÖNETİMİ & ÖNCELİK =====================

def _bg_sync_provider(provider_id: int):
    from .database import SessionLocal
    from .sync_service import sync_provider
    db = SessionLocal()
    try:
        p = db.query(Provider).get(provider_id)
        if p:
            sync_provider(db, p)
    except Exception as exc:
        logger.error(f"Arka plan sync hatası (provider {provider_id}): {exc}")
    finally:
        db.close()

@router.post("/providers")
async def add_provider(
    background_tasks: BackgroundTasks,
    name: Optional[str] = Form(None),
    m3u_url: Optional[str] = Form(None),
    server_url: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    from .m3u_parser import extract_xtream_credentials, test_xtream_handshake

    # Son öncelik değerini bulup sona ekle
    max_prio = db.query(Provider.priority).order_by(Provider.priority.desc()).first()
    next_prio = (max_prio[0] + 1) if max_prio else 1

    clean_m3u = (m3u_url or "").strip()

    # 1. M3U URL ile Ekleme
    if clean_m3u:
        creds = extract_xtream_credentials(clean_m3u)
        xtream_ok = False
        if creds:
            # Xtream Codes el sıkışmasını test et
            xtream_ok = test_xtream_handshake(creds["server_url"], creds["username"], creds["password"])

        if xtream_ok and creds:
            # Xtream başarılı -> Standart Xtream olarak kaydet
            prov_name = (name or "").strip() or creds["server_url"].split("//")[-1].split(":")[0]
            provider = Provider(
                name=prov_name,
                server_url=creds["server_url"],
                username=creds["username"],
                password_enc=crypto_util.encrypt(creds["password"]),
                adapter_type="standard",
                last_sync_status="syncing",
                priority=next_prio,
                enabled=True,
            )
            db.add(provider)
            db.commit()
            background_tasks.add_task(_bg_sync_provider, provider.id)
            return RedirectResponse("/?msg=provider_added_xtream", status_code=303)
        else:
            # Xtream başarısız veya saf M3U -> Direct M3U olarak kaydet
            prov_name = (name or "").strip() or "M3U Çalma Listesi"
            provider = Provider(
                name=prov_name,
                server_url=clean_m3u,
                username="m3u",
                password_enc="",
                adapter_type="direct_source",
                last_sync_status="syncing",
                priority=next_prio,
                enabled=True,
            )
            db.add(provider)
            db.commit()
            background_tasks.add_task(_bg_sync_provider, provider.id)
            return RedirectResponse("/?msg=provider_added_m3u", status_code=303)

    # 2. Standart Form ile Manuel Ekleme
    srv = (server_url or "").strip().rstrip("/")
    if not srv.startswith("http"):
        srv = "http://" + srv

    prov_name = (name or "").strip() or srv.split("//")[-1]
    provider = Provider(
        name=prov_name,
        server_url=srv,
        username=(username or "").strip(),
        password_enc=crypto_util.encrypt(password or ""),
        adapter_type="standard",
        last_sync_status="syncing",
        priority=next_prio,
        enabled=True,
    )
    db.add(provider)
    db.commit()
    background_tasks.add_task(_bg_sync_provider, provider.id)
    return RedirectResponse("/?msg=provider_added", status_code=303)

@router.post("/providers/{provider_id}/priority")
async def change_provider_priority(
    provider_id: int,
    direction: str = Form(...), # "up" or "down"
    db: Session = Depends(get_db)
):
    providers = db.query(Provider).order_by(Provider.priority.asc(), Provider.id.asc()).all()
    idx = next((i for i, p in enumerate(providers) if p.id == provider_id), None)
    if idx is not None:
        if direction == "up" and idx > 0:
            target = providers[idx - 1]
            p1, p2 = providers[idx].priority, target.priority
            if p1 == p2:
                providers[idx].priority = idx - 1
                target.priority = idx
            else:
                providers[idx].priority, target.priority = target.priority, providers[idx].priority
            db.commit()
        elif direction == "down" and idx < len(providers) - 1:
            target = providers[idx + 1]
            p1, p2 = providers[idx].priority, target.priority
            if p1 == p2:
                providers[idx].priority = idx + 1
                target.priority = idx
            else:
                providers[idx].priority, target.priority = target.priority, providers[idx].priority
            db.commit()

    return RedirectResponse("/", status_code=303)

@router.post("/providers/{provider_id}/toggle")
async def toggle_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(Provider).get(provider_id)
    if provider:
        provider.enabled = not provider.enabled
        db.commit()
    return RedirectResponse("/", status_code=303)

@router.post("/providers/{provider_id}/delete")
async def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(Provider).get(provider_id)
    if provider:
        db.delete(provider)
        db.commit()
    return RedirectResponse("/", status_code=303)


@router.post("/sync")
async def manual_sync(request: Request, db: Session = Depends(get_db)):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)
    run_sync_all()
    providers = db.query(Provider).order_by(Provider.priority.asc(), Provider.id.asc()).all()
    return templates.TemplateResponse(request, "partials/stats.html", {"providers": providers, "req": request})

@router.get("/providers/{provider_id}", response_class=HTMLResponse)
async def provider_detail(request: Request, provider_id: int, db: Session = Depends(get_db)):
    if settings_manager.has_panel_password() and not _check_panel_auth(request):
        return RedirectResponse("/login", status_code=303)
    provider = db.query(Provider).get(provider_id)
    if not provider:
        return RedirectResponse("/", status_code=303)
    cats = _sort_cats(db, provider_id)
    streams = db.query(Stream).filter(Stream.provider_id == provider_id).count()

    return templates.TemplateResponse(
        request, "provider.html",
        {"provider": provider, "categories": cats, "streams": streams, "req": request}
    )

@router.post("/categories/{category_id}/toggle")
async def toggle_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).get(category_id)
    if cat:
        cat.enabled = not cat.enabled
        cat.is_new = False
        db.commit()
        db.query(Stream).filter(Stream.category_id == cat.id).update({"enabled": cat.enabled})
        db.commit()
        return {"status": "ok", "category_id": cat.id, "enabled": cat.enabled}
    return RedirectResponse(f"/providers/{cat.provider_id}" if cat else "/", status_code=303)

@router.post("/categories/group/bulk")
async def bulk_toggle_group_categories(
    request: Request,
    provider_id: int = Form(...),
    content_type: str = Form(...),
    group_name: str = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db)
):
    if content_type not in ("live", "vod", "series"):
        raise HTTPException(400, "Invalid content_type")
    enable = (action == "enable")

    all_type_cats = db.query(Category).filter(
        Category.provider_id == provider_id,
        Category.content_type == content_type,
        Category.is_active == True
    ).all()

    target_cat_ids = [
        c.id for c in all_type_cats
        if (c.parent_name or detect_category_group(c.name)) == group_name
    ]

    if target_cat_ids:
        db.query(Category).filter(Category.id.in_(target_cat_ids)).update(
            {"enabled": enable, "is_new": False}, synchronize_session=False
        )
        db.query(Stream).filter(Stream.category_id.in_(target_cat_ids)).update(
            {"enabled": enable}, synchronize_session=False
        )
        db.commit()

    if request.headers.get("hx-request") == "true":
        provider = db.query(Provider).get(provider_id)
        cats = [c for c in _sort_cats(db, provider_id) if c.content_type == content_type]
        return templates.TemplateResponse(
            request, "partials/category_section.html",
            {"provider": provider, "categories": cats, "section_cats": cats, "content_type": content_type, "req": request}
        )
    return {"status": "ok", "enabled": enable, "count": len(target_cat_ids)}

@router.post("/categories/{content_type}/bulk")
async def bulk_toggle_categories(
    request: Request, content_type: str,
    action: str = Form(...), provider_id: int = Form(...),
    db: Session = Depends(get_db)
):
    if content_type not in ("live", "vod", "series"):
        raise HTTPException(400, "Invalid content_type")
    enable = action == "enable"
    db.query(Category).filter(
        Category.provider_id == provider_id,
        Category.content_type == content_type,
        Category.is_active == True
    ).update({"enabled": enable, "is_new": False})
    db.query(Stream).filter(
        Stream.provider_id == provider_id,
        Stream.content_type == content_type,
        Stream.is_active == True
    ).update({"enabled": enable})
    db.commit()
    
    if request.headers.get("hx-request") == "true":
        provider = db.query(Provider).get(provider_id)
        cats = [c for c in _sort_cats(db, provider_id) if c.content_type == content_type]
        return templates.TemplateResponse(
            request, "partials/category_section.html",
            {"provider": provider, "categories": cats, "section_cats": cats, "content_type": content_type, "req": request}
        )
    return {"status": "ok", "enabled": enable}

@router.post("/providers/{provider_id}/group/bulk")
async def bulk_toggle_provider_group(
    request: Request,
    provider_id: int,
    group_name: str = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db)
):
    enable = (action == "enable")
    all_cats = db.query(Category).filter(
        Category.provider_id == provider_id,
        Category.is_active == True
    ).all()

    target_cat_ids = [
        c.id for c in all_cats
        if (c.parent_name or detect_category_group(c.name)) == group_name
    ]

    if target_cat_ids:
        db.query(Category).filter(Category.id.in_(target_cat_ids)).update(
            {"enabled": enable, "is_new": False}, synchronize_session=False
        )
        db.query(Stream).filter(Stream.category_id.in_(target_cat_ids)).update(
            {"enabled": enable}, synchronize_session=False
        )
        db.commit()

    return RedirectResponse(f"/providers/{provider_id}", status_code=303)

@router.post("/categories/{category_id}/sort")
async def sort_category(
    request: Request,
    category_id: int,
    direction: str = Form(...), # "up" or "down"
    content_type: str = Form(...),
    provider_id: int = Form(...),
    db: Session = Depends(get_db)
):
    cats = db.query(Category).filter(
        Category.provider_id == provider_id,
        Category.content_type == content_type
    ).order_by(Category.sort_order.asc(), Category.id.asc()).all()

    # Sıralama numaralarını normalize et
    for idx, c in enumerate(cats):
        c.sort_order = idx

    cur_idx = next((i for i, c in enumerate(cats) if c.id == category_id), None)
    if cur_idx is not None:
        if direction == "up" and cur_idx > 0:
            cats[cur_idx].sort_order, cats[cur_idx - 1].sort_order = cur_idx - 1, cur_idx
            db.commit()
        elif direction == "down" and cur_idx < len(cats) - 1:
            cats[cur_idx].sort_order, cats[cur_idx + 1].sort_order = cur_idx + 1, cur_idx
            db.commit()

    provider = db.query(Provider).get(provider_id)
    updated_cats = db.query(Category).filter(
        Category.provider_id == provider_id,
        Category.content_type == content_type
    ).order_by(Category.sort_order.asc(), Category.id.asc()).all()

    return templates.TemplateResponse(
        request, "partials/category_section.html",
        {"provider": provider, "categories": updated_cats, "section_cats": updated_cats, "content_type": content_type, "req": request}
    )

@router.get("/categories/{category_id}/streams")
async def category_streams_list(request: Request, category_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).get(category_id)
    if not cat:
        raise HTTPException(404, "Kategori bulunamadı")
    streams = db.query(Stream).filter(
        Stream.category_id == category_id,
        Stream.is_active == True
    ).order_by(Stream.name.asc()).all()
    return templates.TemplateResponse(
        request, "partials/channel_list.html",
        {"category": cat, "streams": streams, "req": request}
    )

@router.post("/streams/{stream_id}/toggle")
async def toggle_stream(stream_id: int, db: Session = Depends(get_db)):
    stream = db.query(Stream).get(stream_id)
    if stream:
        stream.enabled = not stream.enabled
        stream.manual_enabled = stream.enabled
        db.commit()
        return {"status": "ok", "stream_id": stream.id, "enabled": stream.enabled}
    raise HTTPException(404, "Kanal bulunamadı")

@router.post("/categories/{category_id}/streams/bulk")
async def bulk_toggle_category_streams(
    request: Request,
    category_id: int,
    action: str = Form(...), # "enable" or "disable"
    db: Session = Depends(get_db)
):
    cat = db.query(Category).get(category_id)
    if not cat:
        raise HTTPException(404, "Kategori bulunamadı")
    enable = (action == "enable")
    db.query(Stream).filter(
        Stream.category_id == category_id,
        Stream.is_active == True
    ).update({"enabled": enable, "manual_enabled": enable})
    db.commit()

    streams = db.query(Stream).filter(
        Stream.category_id == category_id,
        Stream.is_active == True
    ).order_by(Stream.name.asc()).all()
    return templates.TemplateResponse(
        request, "partials/channel_list.html",
        {"category": cat, "streams": streams, "req": request}
    )