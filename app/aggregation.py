"""Multi-provider Aggregation ve Duplicate Kanal Yönetimi Servisi.

Bu modül:
1. Birden fazla aktif sağlayıcıyı öncelik (priority) sırasına göre birleştirir.
2. Aynı kanalları güvenli şekilde tespit edip deduplication uygular (yüksek öncelikli olanı seçer).
3. EPG, M3U ve Xtream Codes API (player_api.php) için birleşik ve çakışmasız çıktı üretir.
4. TiviMate gibi oynatıcılar için direct stream yönlendirmesi sağlar.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import Request
from sqlalchemy.orm import Session

from .models import Category, EpgProgram, Provider, Stream
from .stream_adapters import get_adapter_for_provider

logger = logging.getLogger(__name__)


def normalize_channel_name(name: str) -> str:
    """Kanal adını küçük harfe çevirir, ülke öneklerini, çözünürlük etiketlerini ve
    özel karakterleri temizleyerek duplicate karşılaştırması için normalize eder.
    
    Örnek:
      'TR | TRT 1 HD' -> 'trt 1'
      'TR: TRT 1 FHD [1080P]' -> 'trt 1'
      'BEIN SPORTS 1 HD' -> 'bein sports 1'
      'BEIN SPORTS 2 HD' -> 'bein sports 2'  (ayrı kanal olarak kalır)
    """
    if not name:
        return ""
    s = name.strip()

    # 1. Ülke/dil öneklerini temizle: "TR: ", "TR | ", "[TR] ", "(TR) ", "DE: ", "FR - " vb.
    s = re.sub(r"^(\[[A-Za-z0-9_]{1,4}\]|\([A-Za-z0-9_]{1,4}\)|[A-Za-z0-9_]{1,4}\s*[:|\-])\s*", "", s)

    # 2. Türkçe karakterleri standart harflere dönüştür (Unicode-safe)
    tr_from = "\u0131\u0130\u011f\u011e\u00fc\u00dc\u015f\u015e\u00f6\u00d6\u00e7\u00c7"
    tr_to = "iIgGuUsSoOcC"
    s = s.translate(str.maketrans(tr_from, tr_to)).lower()

    # 3. Çözünürlük, kalite ve yayın tipi takılarını temizle (kelime sınırları veya parantezler içinde)
    quality_patterns = r"(fhd|uhd|4k|hd|sd|hevc|h\.?265|1080p|720p|50fps|raw|vip|backup|yedek)"
    s = re.sub(rf"\[{quality_patterns}\]", " ", s)
    s = re.sub(rf"\({quality_patterns}\)", " ", s)
    s = re.sub(rf"\b{quality_patterns}\b", " ", s)

    # 4. Noktalama işaretleri ve ayraçları boşluğa çevir
    s = re.sub(r"[.\-_|/\\*+:]", " ", s)

    # 5. Boşlukları sadeleştir
    s = re.sub(r"\s+", " ", s).strip()

    return s if s else name.strip().lower()


def get_active_providers(db: Session) -> List[Provider]:
    """Aktif (enabled=True ve sync durumu 'ok') sağlayıcıları öncelik (priority ASC)
    ve id sırasına göre getirir."""
    return db.query(Provider).filter(
        Provider.enabled == True,
        Provider.last_sync_status == "ok"
    ).order_by(Provider.priority.asc(), Provider.id.asc()).all()


def get_aggregated_categories(db: Session, ctype: str) -> Tuple[List[dict], Dict[Tuple[int, str], str]]:
    """Tüm aktif sağlayıcıların aktif kategorilerini toplar.
    Dönüş:
      (kategori_listesi, provider_ve_kategori_id_esleme_haritasi)
    """
    providers = get_active_providers(db)
    aggregated_cats: List[dict] = []
    seen_cat_names: Dict[str, str] = {}  # norm_name -> aggregated_cat_id
    cat_id_mapping: Dict[Tuple[int, str], str] = {}  # (provider_id, provider_category_id) -> aggregated_cat_id

    for prov in providers:
        cats = db.query(Category).filter(
            Category.provider_id == prov.id,
            Category.content_type == ctype,
            Category.enabled == True,
            Category.is_active == True,
        ).order_by(Category.sort_order, Category.name).all()

        for c in cats:
            norm_name = c.name.strip().lower()
            if norm_name in seen_cat_names:
                agg_id = seen_cat_names[norm_name]
            else:
                agg_id = str(c.id)
                seen_cat_names[norm_name] = agg_id
                aggregated_cats.append({
                    "category_id": agg_id,
                    "category_name": c.name.strip(),
                    "parent_id": 0,
                })
            cat_id_mapping[(prov.id, str(c.provider_category_id))] = agg_id

    return aggregated_cats, cat_id_mapping


def get_aggregated_streams(
    db: Session,
    ctype: str,
    filter_category_id: Optional[str] = None
) -> Tuple[List[dict], List[Stream]]:
    """Tüm aktif sağlayıcılardan içerikleri çeker.
    Sağlayıcı önceliğine göre duplicate olan kanalları eler.
    Dönüş:
      (xtream_stream_dicts, deduplicated_stream_models)
    """
    providers = get_active_providers(db)
    aggregated_cats, cat_id_map = get_aggregated_categories(db, ctype)

    seen_channel_keys: Dict[str, Stream] = {}
    deduped_streams: List[Stream] = []
    stream_output_list: List[dict] = []

    # Sağlayıcı önceliğine göre (küçük priority önce) tara
    for prov in providers:
        # Bu sağlayıcının aktif kategorileri
        enabled_cat_rows = db.query(Category.provider_category_id).filter(
            Category.provider_id == prov.id,
            Category.content_type == ctype,
            Category.enabled == True,
            Category.is_active == True,
        ).all()
        enabled_cat_ids = [str(r[0]) for r in enabled_cat_rows]
        if not enabled_cat_ids:
            continue

        q = db.query(Stream).filter(
            Stream.provider_id == prov.id,
            Stream.content_type == ctype,
            Stream.enabled == True,
            Stream.is_active == True,
            Stream.provider_category_id.in_(enabled_cat_ids),
        ).order_by(Stream.id.asc())

        streams = q.all()

        for s in streams:
            # Normalizasyon anahtarı (Deduplication)
            key = normalize_channel_name(s.name)
            if key in seen_channel_keys:
                # Daha yüksek öncelikli bir sağlayıcıda zaten mevcut, duplicate olarak atla
                continue

            seen_channel_keys[key] = s
            deduped_streams.append(s)

            agg_cat_id = cat_id_map.get((prov.id, str(s.provider_category_id)), str(s.category_id))

            # Kategori filtresi verilmişse kontrol et
            if filter_category_id and str(agg_cat_id) != str(filter_category_id):
                continue

            if ctype == "live":
                stream_output_list.append({
                    "num": s.id,
                    "name": s.name,
                    "stream_type": "live",
                    "stream_id": s.id,
                    "stream_icon": s.stream_icon or "",
                    "epg_channel_id": str(s.id),
                    "added": "",
                    "category_id": agg_cat_id,
                    "custom_sid": "",
                    "tv_archive": 0,
                    "direct_source": "",
                    "tv_archive_duration": 0,
                })
            elif ctype == "vod":
                stream_output_list.append({
                    "num": s.id,
                    "name": s.name,
                    "stream_type": "movie",
                    "stream_id": s.id,
                    "stream_icon": s.stream_icon or "",
                    "rating": s.rating or 0,
                    "rating_5based": 0,
                    "added": s.added_at or "",
                    "category_id": agg_cat_id,
                    "container_extension": s.extension or "mp4",
                    "direct_source": "",
                })
            elif ctype == "series":
                stream_output_list.append({
                    "series_id": s.id,
                    "name": s.name,
                    "cover": s.stream_icon or "",
                    "plot": s.description or "",
                    "cast": "",
                    "director": "",
                    "genre": "",
                    "releaseDate": s.year or "",
                    "last_modified": s.added_at or "",
                    "rating": s.rating or 0,
                    "rating_5based": 0,
                    "category_id": agg_cat_id,
                })

    return stream_output_list, deduped_streams


def get_aggregated_m3u(db: Session, request: Request, ctype_filter: Optional[str] = None) -> str:
    """Tüm aktif sağlayıcıların içeriklerinden deduplicated M3U çalma listesi üretir."""
    lines = [f'#EXTM3U url-tvg="http://{request.client.host}:{request.url.port or 8000}/xmltv.php"']

    ctypes = [("live", "Live TV"), ("vod", "VOD"), ("series", "Series")]
    if ctype_filter:
        ctypes = [(ctype_filter, ctype_filter.upper())]

    for ctype, label in ctypes:
        _, deduped_streams = get_aggregated_streams(db, ctype)
        _, cat_id_map = get_aggregated_categories(db, ctype)

        for s in deduped_streams:
            prov = s.provider
            adapter = get_adapter_for_provider(prov)

            cat = s.category
            group = cat.name if cat else label
            logo = s.stream_icon or ""

            if ctype == "live":
                play_url = adapter.build_live_url(prov, s).url
            elif ctype == "vod":
                play_url = adapter.build_vod_url(prov, s).url
            else:
                play_url = adapter.build_series_url(prov, s).url

            lines.append(f'#EXTINF:-1 tvg-id="{s.id}" tvg-name="{s.name}" tvg-logo="{logo}" group-title="{group}",{s.name}')
            lines.append(play_url)

    return "\n".join(lines)


def get_aggregated_xmltv(db: Session) -> str:
    """Sadece aktif/filtrelenmiş ve tekilleştirilmiş kanalların XMLTV EPG çıktısını üretir."""
    _, deduped_live = get_aggregated_streams(db, "live")
    now = datetime.utcnow()

    lines = ['<?xml version="1.0" encoding="utf-8"?>', '<tv generator-info-name="Xtream-Filter">']

    # 1. Kanallar (<channel id="X">)
    for s in deduped_live:
        lines.append(f'  <channel id="{s.id}">')
        lines.append(f'    <display-name>{s.name}</display-name>')
        if s.stream_icon:
            lines.append(f'    <icon src="{s.stream_icon}"/>')
        lines.append('  </channel>')

    # 2. Programlar (<programme>)
    for s in deduped_live:
        epgs = db.query(EpgProgram).filter(
            EpgProgram.provider_id == s.provider_id,
            EpgProgram.channel_id == s.provider_stream_id,
            EpgProgram.is_active == True,
            EpgProgram.start >= now - timedelta(days=1),
            EpgProgram.start <= now + timedelta(days=7),
        ).order_by(EpgProgram.start).all()

        seen_intervals = set()
        for e in epgs:
            interval_key = (e.start, e.end)
            if interval_key in seen_intervals:
                continue
            seen_intervals.add(interval_key)

            start_str = e.start.strftime("%Y%m%d%H%M%S") + " +0000"
            stop_str = e.end.strftime("%Y%m%d%H%M%S") + " +0000"
            lines.append(f'  <programme start="{start_str}" stop="{stop_str}" channel="{s.id}">')
            lines.append(f'    <title lang="tr">{e.title}</title>')
            if e.description:
                lines.append(f'    <desc lang="tr">{e.description}</desc>')
            lines.append('  </programme>')

    lines.append('</tv>')
    return "\n".join(lines)


def resolve_stream_playback_url(db: Session, raw_stream_id: str, ctype: str = "live") -> Optional[str]:
    """TiviMate gibi Xtream client'lar /live/... veya /{user}/{pass}/{id} istediğinde
    Stream ID'den doğru Provider ve Stream modelini bulup direct URL'i üretir."""
    # Uzantıyı ayıkla (99.ts -> 99, 99.mp4 -> 99, 99 -> 99)
    clean_id = raw_stream_id.split(".")[0]
    stream = None
    if clean_id.isdigit():
        stream = db.query(Stream).get(int(clean_id))

    if not stream or not stream.provider:
        stream = db.query(Stream).filter(Stream.provider_stream_id == clean_id).first()

    if not stream or not stream.provider:
        return None

    prov = stream.provider
    adapter = get_adapter_for_provider(prov)

    # Stream'in kendi gerçek içerik türünü kullan
    stream_type = stream.content_type or ctype
    if stream_type == "vod":
        return adapter.build_vod_url(prov, stream).url
    elif stream_type == "series":
        return adapter.build_series_url(prov, stream).url
    else:
        return adapter.build_live_url(prov, stream).url
