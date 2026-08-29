"""Kendi Xtream API Output — IPTV uygulamaları buna bağlanır (Direct Stream URL)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import httpx
from sqlalchemy.orm import Session

from . import config, crypto_util, settings_manager
from .database import get_db
from .models import Category, Provider, Stream, EpgProgram
from .stream_adapters import get_adapter_for_provider

router = APIRouter()
security = HTTPBasic(auto_error=False)
logger = logging.getLogger(__name__)

def _is_api_auth_valid(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()
    if not expected_pass:
        return True

    if credentials:
        return credentials.username == expected_user and credentials.password == expected_pass

    q_user = username or request.query_params.get("username")
    q_pass = password or request.query_params.get("password")
    if q_user is not None or q_pass is not None:
        return q_user == expected_user and q_pass == expected_pass

    return False

def verify_api_credentials(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    expected_pass = settings_manager.get_api_password()
    if not expected_pass:
        return
    if not _is_api_auth_valid(request, credentials):
        raise HTTPException(401, "Invalid API credentials", headers={"WWW-Authenticate": "Basic"})


from fastapi.responses import RedirectResponse
from . import aggregation

def get_active_providers_or_503(db: Session) -> list[Provider]:
    providers = aggregation.get_active_providers(db)
    if not providers:
        raise HTTPException(503, "Aktif sağlayıcı yok. Panelden ekleyip senkronize edin.")
    return providers

# ===================== PLAYER API =====================

@router.api_route("/player_api.php", methods=["GET", "POST"])
async def player_api(
    request: Request,
    db: Session = Depends(get_db),
    action: Optional[str] = None,
    stream_id: Optional[str] = None,
    category_id: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    if request.method == "POST":
        try:
            form = await request.form()
            action = action or form.get("action")
            stream_id = stream_id or form.get("stream_id")
            category_id = category_id or form.get("category_id")
            username = username or form.get("username")
            password = password or form.get("password")
        except Exception:
            pass

    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()

    # Kimlik kontrolü
    if expected_pass:
        if not _is_api_auth_valid(request, credentials, username, password):
            if action is None:
                return {"user_info": {"auth": 0}}
            raise HTTPException(401, "Invalid API credentials", headers={"WWW-Authenticate": "Basic"})

    providers = get_active_providers_or_503(db)

    # 1. User Info & Server Info (Handshake / Auth)
    if action is None:
        first_prov = providers[0]
        host_header = request.headers.get("host")
        if host_header:
            srv_url = f"http://{host_header}"
            srv_port = host_header.split(":")[1] if ":" in host_header else "80"
        else:
            srv_url = f"http://{config.APP_HOST}:{config.APP_PORT}"
            srv_port = str(config.APP_PORT)

        return {
            "user_info": {
                "username": expected_user,
                "password": expected_pass,
                "message": "Xtream Filter (Aggregated)",
                "auth": 1,
                "status": "Active",
                "exp_date": None,
                "is_trial": "0",
                "active_cons": "1",
                "created_at": first_prov.created_at.strftime("%Y-%m-%d %H:%M:%S") if first_prov.created_at else "",
                "max_connections": "1",
                "allowed_output_formats": ["m3u8", "ts"]
            },
            "server_info": {
                "url": srv_url,
                "port": srv_port,
                "https_port": "0",
                "server_protocol": "http",
                "rtmp_port": "0",
                "timezone": "Europe/Istanbul",
                "timestamp_now": int(datetime.now().timestamp()),
                "time_now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    # 2. Aggregated Kategoriler
    cat_map = {"get_live_categories": "live", "get_vod_categories": "vod", "get_series_categories": "series"}
    if action in cat_map:
        ctype = cat_map[action]
        cats, _ = aggregation.get_aggregated_categories(db, ctype)
        return cats

    # 3. Aggregated Streams (Deduplicated & Ordered by Provider Priority)
    stream_map = {"get_live_streams": "live", "get_vod_streams": "vod", "get_series": "series"}
    if action in stream_map:
        ctype = stream_map[action]
        cat_id = category_id or request.query_params.get("category_id")
        streams_out, _ = aggregation.get_aggregated_streams(db, ctype, filter_category_id=cat_id)
        return streams_out

    # 4. EPG Detayları (Tekil kanal)
    if action == "get_short_epg" and stream_id:
        clean_id = str(stream_id).split(".")[0]
        stream = db.query(Stream).get(int(clean_id)) if clean_id.isdigit() else None
        if not stream:
            stream = db.query(Stream).filter(Stream.provider_stream_id == str(stream_id)).first()

        if stream:
            now = datetime.utcnow()
            epgs = db.query(EpgProgram).filter(
                EpgProgram.provider_id == stream.provider_id,
                EpgProgram.channel_id == stream.provider_stream_id,
                EpgProgram.is_active == True,
                EpgProgram.start >= now - timedelta(days=1),
                EpgProgram.start <= now + timedelta(days=7)
            ).order_by(EpgProgram.start).limit(500).all()

            seen_intervals = set()
            listings = []
            for e in epgs:
                if (e.start, e.end) in seen_intervals:
                    continue
                seen_intervals.add((e.start, e.end))
                listings.append({
                    "start": int(e.start.timestamp()),
                    "end": int(e.end.timestamp()),
                    "title": e.title,
                    "description": e.description or ""
                })
            return {"epg_listings": listings}

        return {"epg_listings": []}

    raise HTTPException(400, f"Bilinmeyen action: {action}")

# ===================== XMLTV EPG =====================

@router.get("/xmltv.php")
async def xmltv_epg(
    request: Request,
    db: Session = Depends(get_db),
    username: Optional[str] = None,
    password: Optional[str] = None,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    expected_pass = settings_manager.get_api_password()
    if expected_pass and not _is_api_auth_valid(request, credentials, username, password):
        raise HTTPException(401, "Invalid API credentials", headers={"WWW-Authenticate": "Basic"})

    get_active_providers_or_503(db)
    xml_content = aggregation.get_aggregated_xmltv(db)
    return Response(content=xml_content, media_type="application/xml")

# ===================== M3U PLAYLIST =====================

@router.get("/get.php")
@router.get("/playlist.m3u")
@router.get("/playlist.m3u8")
@router.get("/get.m3u")
@router.get("/get.m3u8")
async def m3u_playlist(
    request: Request,
    db: Session = Depends(get_db),
    username: Optional[str] = None,
    password: Optional[str] = None,
    type: Optional[str] = None,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
):
    expected_pass = settings_manager.get_api_password()
    if expected_pass and not _is_api_auth_valid(request, credentials, username, password):
        raise HTTPException(401, "Invalid API credentials", headers={"WWW-Authenticate": "Basic"})

    get_active_providers_or_503(db)
    m3u_content = aggregation.get_aggregated_m3u(db, request, ctype_filter=type)
    return Response(
        content=m3u_content,
        media_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": 'inline; filename="playlist.m3u"',
            "Content-Type": "audio/x-mpegurl; charset=utf-8",
        }
    )

# ===================== STREAM PLAYBACK (Direct 302 vs Stream Proxy) =====================

STREAM_USER_AGENT = "VLC/3.0.20 LibVLC/3.0.20"

async def proxy_stream_response(upstream_url: str, request: Request):
    """Video akışını sunucu üzerinden istemciye proxy eder (Reverse Stream Proxy)."""
    headers = {
        "User-Agent": STREAM_USER_AGENT,
        "Accept": "*/*",
    }
    if "range" in request.headers:
        headers["Range"] = request.headers["range"]

    client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(connect=15.0, read=None, write=15.0, pool=None)
    )

    try:
        req = client.build_request(request.method, upstream_url, headers=headers)
        upstream_resp = await client.send(req, stream=True)
    except Exception as exc:
        await client.aclose()
        logger.error("Proxy stream upstream hatası (%s): %s", upstream_url, exc)
        raise HTTPException(502, f"Sağlayıcıya bağlanılamadı: {exc}")

    if request.method == "HEAD":
        resp_headers = dict(upstream_resp.headers)
        status_code = upstream_resp.status_code
        await upstream_resp.aclose()
        await client.aclose()
        return Response(status_code=status_code, headers=resp_headers)

    if upstream_resp.status_code >= 400:
        status_code = upstream_resp.status_code
        await upstream_resp.aclose()
        await client.aclose()
        raise HTTPException(status_code, "Sağlayıcı yayın hatası döndürdü")

    response_headers = {}
    for h in ("content-type", "content-length", "content-range", "accept-ranges"):
        if h in upstream_resp.headers:
            response_headers[h] = upstream_resp.headers[h]

    media_type = upstream_resp.headers.get("content-type") or "video/mp2t"

    async def stream_generator():
        try:
            async for chunk in upstream_resp.aiter_bytes(chunk_size=65536):
                yield chunk
        except Exception:
            pass
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=upstream_resp.status_code,
        headers=response_headers,
        media_type=media_type,
    )


@router.api_route("/live/{username}/{password}/{stream_id}", methods=["GET", "HEAD"])
async def play_live_stream(
    username: str,
    password: str,
    stream_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()
    if expected_pass:
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "Invalid credentials")

    play_url = aggregation.resolve_stream_playback_url(db, stream_id, ctype="live")
    if not play_url:
        raise HTTPException(404, "Canlı yayın akışı bulunamadı")

    if not settings_manager.is_stream_proxy_enabled():
        return RedirectResponse(url=play_url, status_code=302)

    return await proxy_stream_response(play_url, request)


@router.api_route("/movie/{username}/{password}/{stream_id}", methods=["GET", "HEAD"])
async def play_movie_stream(
    username: str,
    password: str,
    stream_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()
    if expected_pass:
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "Invalid credentials")

    play_url = aggregation.resolve_stream_playback_url(db, stream_id, ctype="vod")
    if not play_url:
        raise HTTPException(404, "Film akışı bulunamadı")

    if not settings_manager.is_stream_proxy_enabled():
        return RedirectResponse(url=play_url, status_code=302)

    return await proxy_stream_response(play_url, request)


@router.api_route("/series/{username}/{password}/{stream_id}", methods=["GET", "HEAD"])
async def play_series_stream(
    username: str,
    password: str,
    stream_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()
    if expected_pass:
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "Invalid credentials")

    play_url = aggregation.resolve_stream_playback_url(db, stream_id, ctype="series")
    if not play_url:
        raise HTTPException(404, "Dizi akışı bulunamadı")

    if not settings_manager.is_stream_proxy_enabled():
        return RedirectResponse(url=play_url, status_code=302)

    return await proxy_stream_response(play_url, request)


@router.api_route("/{username}/{password}/{stream_id}", methods=["GET", "HEAD"])
@router.api_route("/play/{username}/{password}/{stream_id}", methods=["GET", "HEAD"])
async def play_generic_stream(
    username: str,
    password: str,
    stream_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    expected_user = settings_manager.get_api_username()
    expected_pass = settings_manager.get_api_password()
    if expected_pass:
        if username != expected_user or password != expected_pass:
            raise HTTPException(401, "Invalid credentials")

    play_url = aggregation.resolve_stream_playback_url(db, stream_id)
    if not play_url:
        raise HTTPException(404, "Yayın akışı bulunamadı")

    if not settings_manager.is_stream_proxy_enabled():
        return RedirectResponse(url=play_url, status_code=302)

    return await proxy_stream_response(play_url, request)