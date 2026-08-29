"""M3U Playlist Parser & Xtream Auto-Detector.
Büyük M3U dosyalarını belleği (RAM) şişirmeden streaming (satır satır) işler.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from typing import Optional, Generator, Dict, Any

import httpx
from sqlalchemy.orm import Session

from . import crypto_util
from .models import Category, Provider, Stream

logger = logging.getLogger(__name__)

USER_AGENT = "VLC/3.0.20 LibVLC/3.0.20"


def extract_xtream_credentials(url: str) -> Optional[dict]:
    """M3U bağlantısından Xtream Server URL, Kullanıcı Adı ve Şifreyi ayıklar."""
    if not url or not url.strip():
        return None

    url_clean = url.strip()
    parsed = urlparse(url_clean)
    if not parsed.scheme or not parsed.netloc:
        return None

    qs = parse_qs(parsed.query)
    username = (qs.get("username") or qs.get("user") or [None])[0]
    password = (qs.get("password") or qs.get("pass") or [None])[0]

    # Parametrelerde yoksa path yapısını kontrol et: /live/USERNAME/PASSWORD/
    if not username or not password:
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) >= 3 and path_parts[0] in ("live", "movie", "series"):
            username = path_parts[1]
            password = path_parts[2]

    if username and password:
        server_url = f"{parsed.scheme}://{parsed.netloc}"
        return {
            "server_url": server_url,
            "username": username,
            "password": password,
        }

    return None


def test_xtream_handshake(server_url: str, username: str, password: str, timeout: float = 6.0) -> bool:
    """Belirtilen bilgilerle Xtream Codes API el sıkışmasını test eder."""
    api_url = f"{server_url.rstrip('/')}/player_api.php"
    params = {"username": username, "password": password}
    headers = {"User-Agent": USER_AGENT}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(api_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    user_info = data.get("user_info", {})
                    # auth == 1 veya Active
                    if user_info.get("auth") == 1 or user_info.get("status") == "Active":
                        return True
    except Exception as exc:
        logger.info(f"Xtream el sıkışma testi başarısız ({server_url}): {exc}")

    return False


def _parse_extinf_line(line: str) -> dict:
    """#EXTINF satırından logo, grup adı, tvg-id ve kanal adını çıkarır."""
    attrs = {}
    attr_matches = re.findall(r'([a-zA-Z0-9_-]+)="([^"]*)"', line)
    for k, v in attr_matches:
        attrs[k.lower()] = v

    comma_idx = line.rfind(",")
    name = line[comma_idx + 1:].strip() if comma_idx != -1 else "Bilinmeyen Kanal"
    # Tırnakları temizle
    name = name.strip('"\'')

    group = attrs.get("group-title") or attrs.get("group") or "Genel"
    logo = attrs.get("tvg-logo") or attrs.get("logo") or ""
    tvg_id = attrs.get("tvg-id") or ""

    return {
        "name": name,
        "group": group.strip(),
        "logo": logo.strip(),
        "tvg_id": tvg_id.strip(),
    }


def _detect_content_type(group: str, url: str) -> str:
    """Grup adına veya dosya uzantısına göre live / vod / series tespit eder."""
    g_lower = group.lower()
    u_lower = url.lower()

    if any(k in g_lower for k in ("dizi", "series", "season", "sezon", "boxset")):
        return "series"
    if any(k in g_lower for k in ("film", "sinema", "vod", "movie")) or any(u_lower.endswith(ext) for ext in (".mp4", ".mkv", ".avi")):
        return "vod"
    return "live"


def stream_parse_m3u(m3u_url: str, timeout: float = 30.0) -> Generator[Dict[str, Any], None, None]:
    """Çok büyük (50-100MB) M3U dosyalarını RAM'e tek seferde yüklemeden satır satır akışla ayrıştırır."""
    headers = {"User-Agent": USER_AGENT}

    with httpx.stream("GET", m3u_url, headers=headers, timeout=timeout, follow_redirects=True) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"M3U URL indirilemedi: HTTP {resp.status_code}")

        current_info = None
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXTINF"):
                current_info = _parse_extinf_line(line)
            elif not line.startswith("#"):
                # URL satırı
                if current_info:
                    stream_url = line
                    ctype = _detect_content_type(current_info["group"], stream_url)
                    yield {
                        "name": current_info["name"],
                        "group": current_info["group"],
                        "logo": current_info["logo"],
                        "tvg_id": current_info["tvg_id"],
                        "url": stream_url,
                        "content_type": ctype,
                    }
                    current_info = None


def sync_m3u_provider(db: Session, provider: Provider) -> dict:
    """M3U tabanlı sağlayıcıyı bellek tasarruflu ve toplu commit'li şekilde senkronize eder."""
    now = datetime.now(timezone.utc)
    m3u_url = provider.server_url

    stats = {"live": 0, "vod": 0, "series": 0, "total": 0}
    cat_cache: dict[tuple[str, str], Category] = {}  # (content_type, group_name) -> Category

    # Mevcut kategorileri önbelleğe al
    existing_cats = db.query(Category).filter(Category.provider_id == provider.id).all()
    for ec in existing_cats:
        cat_cache[(ec.content_type, ec.name)] = ec

    # Mevcut streamleri provider_stream_id veya stream_source ile indexle
    existing_streams = {s.provider_stream_id: s for s in db.query(Stream).filter(Stream.provider_id == provider.id).all()}

    idx = 0
    batch_count = 0

    try:
        for item in stream_parse_m3u(m3u_url):
            idx += 1
            ctype = item["content_type"]
            group_name = item["group"]
            cat_key = (ctype, group_name)

            # Kategori var mı?
            category = cat_cache.get(cat_key)
            if not category:
                # Kategori oluştur
                from .category_grouper import detect_category_group
                parent_grp = detect_category_group(group_name)
                cat_id_slug = f"cat_{len(cat_cache) + 1}"
                category = Category(
                    provider_id=provider.id,
                    content_type=ctype,
                    provider_category_id=cat_id_slug,
                    name=group_name,
                    parent_name=parent_grp,
                    enabled=True,  # M3U sağlayıcı eklendiğinde varsayılan aktif gelsin
                    is_new=True,
                    is_active=True,
                    last_seen_at=now,
                    sort_order=len(cat_cache),
                )
                db.add(category)
                db.flush()  # ID alması için
                cat_cache[cat_key] = category
            else:
                category.is_active = True
                category.last_seen_at = now
                if not category.parent_name:
                    from .category_grouper import detect_category_group
                    category.parent_name = detect_category_group(group_name)

            sid = f"m3u_{idx}"
            existing = existing_streams.get(sid)
            if existing:
                existing.name = item["name"]
                existing.stream_source = item["url"]
                existing.stream_icon = item["logo"]
                existing.provider_category_id = category.provider_category_id
                existing.is_active = True
                existing.last_seen_at = now
            else:
                new_s = Stream(
                    provider_id=provider.id,
                    category_id=category.id,
                    content_type=ctype,
                    provider_stream_id=sid,
                    name=item["name"],
                    provider_category_id=category.provider_category_id,
                    is_active=True,
                    enabled=True,
                    last_seen_at=now,
                    stream_icon=item["logo"],
                    stream_source=item["url"],
                )
                db.add(new_s)

            stats[ctype] += 1
            stats["total"] += 1
            batch_count += 1

            # Her 500 kayıtta bir commit at (SQLite kilidini ve RAM'i korur)
            if batch_count >= 500:
                db.commit()
                batch_count = 0

        # Son kalanları commit'le
        db.commit()

        provider.last_sync_at = now
        provider.last_sync_status = "ok"
        provider.last_sync_error = None
        db.commit()

    except Exception as exc:
        db.rollback()
        provider.last_sync_at = now
        provider.last_sync_status = "error"
        provider.last_sync_error = f"M3U işleme hatası: {exc}"
        db.commit()
        raise

    return stats
