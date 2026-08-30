"""Sağlayıcıdan veri çekip lokal DB'ye senkronize eden servis."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from . import crypto_util
from .models import Category, Provider, Stream, EpgProgram
from .xtream_client import XtreamClient

logger = logging.getLogger(__name__)

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def sync_provider(db: Session, provider: Provider) -> dict:
    if provider.adapter_type == "direct_source":
        from .m3u_parser import sync_m3u_provider
        return sync_m3u_provider(db, provider)

    password = crypto_util.decrypt(provider.password_enc)
    client = XtreamClient(provider.server_url, provider.username, password)

    try:
        auth = client.get_auth()
        user_info = auth.get("user_info", {})
        if user_info.get("status") != "Active":
            raise RuntimeError(f"Xtream hesap aktif değil: {user_info.get('status')}")
    except Exception as exc:
        provider.last_sync_status = "error"
        provider.last_sync_error = f"Auth başarısız: {exc}"
        provider.last_sync_at = _now_utc()
        db.commit()
        raise

    now = _now_utc()
    stats = {"live": 0, "vod": 0, "series": 0, "epg": 0}

    # Kategoriler ve İçerikler
    for ctype in ("live", "vod", "series"):
        try:
            if ctype == "live":
                cats = client.get_live_categories()
                streams = client.get_live_streams()
            elif ctype == "vod":
                cats = client.get_vod_categories()
                streams = client.get_vod_streams()
            else:
                cats = client.get_series_categories()
                streams = client.get_series()
            
            sync_categories(db, provider, ctype, cats, now)
            stats[ctype] = sync_streams(db, provider, ctype, streams, now)
        except Exception as exc:
            logger.error(f"{ctype} sync hatası: {exc}")
            continue

    # EPG
    try:
        live_ids = [str(s.provider_stream_id) for s in db.query(Stream).filter(
            Stream.provider_id == provider.id, Stream.content_type == "live").all()]
        if live_ids:
            epg_raw = client.get_epg(live_ids)
            stats["epg"] = sync_epg(db, provider, epg_raw, now)
    except Exception as exc:
        logger.warning(f"EPG sync hatası: {exc}")

    mark_missing_inactive(db, provider, now)
    
    provider.last_sync_at = now
    provider.last_sync_status = "ok"
    provider.last_sync_error = None
    db.commit()
    from .aggregation import invalidate_aggregation_cache
    invalidate_aggregation_cache()
    return stats

def sync_categories(db: Session, provider: Provider, ctype: str, cats: list[dict], now: datetime):
    from .category_grouper import detect_category_group
    for idx, raw in enumerate(cats or []):
        cid = str(raw.get("category_id", ""))
        name = str(raw.get("category_name", cid)).strip()
        parent_grp = detect_category_group(name)
        
        existing = db.query(Category).filter(
            Category.provider_id == provider.id,
            Category.content_type == ctype,
            Category.provider_category_id == cid
        ).first()

        if existing:
            existing.name = name
            existing.parent_name = parent_grp
            existing.is_active = True
            existing.last_seen_at = now
            existing.sort_order = idx
        else:
            db.add(Category(
                provider_id=provider.id, content_type=ctype,
                provider_category_id=cid, name=name,
                parent_name=parent_grp,
                enabled=True, is_new=True, is_active=True,
                last_seen_at=now, sort_order=idx
            ))
    db.commit()

def sync_streams(db: Session, provider: Provider, ctype: str, streams: list[dict], now: datetime) -> int:
    count = 0
    # Kategori mapping: provider_category_id -> Category.id
    cat_map = {
        c.provider_category_id: c.id
        for c in db.query(Category).filter(
            Category.provider_id == provider.id,
            Category.content_type == ctype
        ).all()
    }
    default_cat_id = next(iter(cat_map.values()), None)
    if default_cat_id is None:
        def_cat = Category(
            provider_id=provider.id, content_type=ctype,
            provider_category_id="default", name="Genel",
            enabled=True, is_new=False, is_active=True, last_seen_at=now, sort_order=0
        )
        db.add(def_cat)
        db.commit()
        default_cat_id = def_cat.id
        cat_map["default"] = default_cat_id

    for raw in streams or []:
        sid = str(raw.get("stream_id") or raw.get("series_id") or "")
        if not sid:
            continue

        name = str(raw.get("name", "Unnamed")).strip()
        cat_id = str(raw.get("category_id", ""))
        actual_cat_id = cat_map.get(cat_id, default_cat_id)

        existing = db.query(Stream).filter(
            Stream.provider_id == provider.id,
            Stream.content_type == ctype,
            Stream.provider_stream_id == sid
        ).first()

        raw_ext = (raw.get("container_extension") or raw.get("target_container") or raw.get("container") or "").strip().lstrip(".") or None
        raw_rating = raw.get("rating")
        try:
            raw_rating = float(raw_rating) if raw_rating is not None and str(raw_rating).strip() != "" else None
        except (ValueError, TypeError):
            raw_rating = None
        raw_year = str(raw.get("year") or raw.get("releaseDate") or raw.get("release_date") or "").strip() or None
        raw_desc = str(raw.get("plot") or raw.get("description") or "").strip() or None
        raw_added = str(raw.get("added") or raw.get("added_at") or "").strip() or None
        raw_icon = raw.get("stream_icon") or raw.get("cover")

        if existing:
            existing.name = name
            existing.is_active = True
            existing.last_seen_at = now
            existing.category_id = actual_cat_id
            existing.provider_category_id = cat_id
            if raw_ext:
                existing.extension = raw_ext
                existing.container = raw_ext
            if raw_icon:
                existing.stream_icon = raw_icon
            if raw_rating is not None:
                existing.rating = raw_rating
            if raw_year:
                existing.year = raw_year
            if raw_desc:
                existing.description = raw_desc
            if raw_added:
                existing.added_at = raw_added
        else:
            new_s = Stream(
                provider_id=provider.id,
                category_id=actual_cat_id,
                content_type=ctype,
                provider_stream_id=sid,
                name=name,
                provider_category_id=cat_id,
                is_active=True,
                last_seen_at=now,
                enabled=True,
                stream_icon=raw_icon,
                extension=raw_ext,
                container=raw_ext,
                rating=raw_rating,
                year=raw_year,
                description=raw_desc,
                added_at=raw_added,
            )
            db.add(new_s)
        count += 1
    db.commit()
    return count

def sync_epg(db: Session, provider: Provider, programs: list[dict], now: datetime) -> int:
    count = 0
    for p in programs or []:
        cid = str(p.get("channel_id") or p.get("stream_id") or "")
        start_ts = p.get("start")
        if not cid or not start_ts: continue
        
        start_dt = datetime.fromtimestamp(int(start_ts), tz=timezone.utc).replace(tzinfo=None)
        
        existing = db.query(EpgProgram).filter(
            EpgProgram.provider_id == provider.id,
            EpgProgram.channel_id == cid,
            EpgProgram.start == start_dt
        ).first()

        if not existing:
            db.add(EpgProgram(
                provider_id=provider.id, channel_id=cid,
                title=p.get("title", "No Title"),
                description=p.get("description"),
                start=start_dt,
                end=datetime.fromtimestamp(int(p.get("end", start_ts)), tz=timezone.utc).replace(tzinfo=None),
                is_active=True, last_seen_at=now
            ))
            count += 1
    db.commit()
    return count

def mark_missing_inactive(db: Session, provider: Provider, now: datetime):
    cutoff = now - timedelta(hours=24)
    db.query(Category).filter(Category.provider_id == provider.id, Category.last_seen_at < cutoff).update({"is_active": False})
    db.query(Stream).filter(Stream.provider_id == provider.id, Stream.last_seen_at < cutoff).update({"is_active": False})
    db.commit()
