"""Kategori üst başlık (ülke/dil/içerik grubu) tespit ve gruplama servisi."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from sqlalchemy.orm import Session

# Ülke ve Dil Haritası: Kod -> (Bayrak/İkon, Başlık)
COUNTRY_MAP: Dict[str, Tuple[str, str]] = {
    "TR": ("🇹🇷", "TR / TÜRKİYE"),
    "TURKIYE": ("🇹🇷", "TR / TÜRKİYE"),
    "TURK": ("🇹🇷", "TR / TÜRKİYE"),
    "TURKISH": ("🇹🇷", "TR / TÜRKİYE"),
    "YERLI": ("🇹🇷", "TR / TÜRKİYE"),
    "DE": ("🇩🇪", "DE / DEUTSCHLAND"),
    "DEUTSCHLAND": ("🇩🇪", "DE / DEUTSCHLAND"),
    "DEUTSCHE": ("🇩🇪", "DE / DEUTSCHLAND"),
    "GERMAN": ("🇩🇪", "DE / DEUTSCHLAND"),
    "GERMANY": ("🇩🇪", "DE / DEUTSCHLAND"),
    "FR": ("🇫🇷", "FR / FRANCE"),
    "FRANCE": ("🇫🇷", "FR / FRANCE"),
    "FRENCH": ("🇫🇷", "FR / FRANCE"),
    "NL": ("🇳🇱", "NL / NEDERLAND"),
    "NEDERLAND": ("🇳🇱", "NL / NEDERLAND"),
    "NETHERLANDS": ("🇳🇱", "NL / NEDERLAND"),
    "DUTCH": ("🇳🇱", "NL / NEDERLAND"),
    "IT": ("🇮🇹", "IT / ITALIA"),
    "ITALIA": ("🇮🇹", "IT / ITALIA"),
    "ITALY": ("🇮🇹", "IT / ITALIA"),
    "ES": ("🇪🇸", "ES / ESPAÑA"),
    "ESPANA": ("🇪🇸", "ES / ESPAÑA"),
    "SPAIN": ("🇪🇸", "ES / ESPAÑA"),
    "SPANISH": ("🇪🇸", "ES / ESPAÑA"),
    "UK": ("🇬🇧", "UK / UNITED KINGDOM"),
    "ENGLAND": ("🇬🇧", "UK / UNITED KINGDOM"),
    "GB": ("🇬🇧", "UK / UNITED KINGDOM"),
    "US": ("🇺🇸", "USA / UNITED STATES"),
    "USA": ("🇺🇸", "USA / UNITED STATES"),
    "AR": ("🇸🇦", "AR / ARABIC"),
    "ARABIEN": ("🇸🇦", "AR / ARABIC"),
    "ARABIC": ("🇸🇦", "AR / ARABIC"),
    "AL": ("🇦🇱", "AL / ALBANIA"),
    "ALBANIA": ("🇦🇱", "AL / ALBANIA"),
    "BA": ("🇧🇦", "BA / BOSNIA"),
    "BOSNIA": ("🇧🇦", "BA / BOSNIA"),
    "BG": ("🇧🇬", "BG / BULGARIA"),
    "BULGARIA": ("🇧🇬", "BG / BULGARIA"),
    "HR": ("🇭🇷", "HR / CROATIA"),
    "CROATIA": ("🇭🇷", "HR / CROATIA"),
    "CZ": ("🇨🇿", "CZ / CZECH"),
    "CZECH": ("🇨🇿", "CZ / CZECH"),
    "EX-YU": ("🌐", "EX-YU / BALKANS"),
    "GR": ("🇬🇷", "GR / GREECE"),
    "GREECE": ("🇬🇷", "GR / GREECE"),
    "GRECEE": ("🇬🇷", "GR / GREECE"),
    "HU": ("🇭🇺", "HU / HUNGARY"),
    "HUNGARY": ("🇭🇺", "HU / HUNGARY"),
    "PL": ("🇵🇱", "PL / POLAND"),
    "POLAND": ("🇵🇱", "PL / POLAND"),
    "POLOND": ("🇵🇱", "PL / POLAND"),
    "PT": ("🇵🇹", "PT / PORTUGAL"),
    "PORTUGAL": ("🇵🇹", "PT / PORTUGAL"),
    "RO": ("🇷🇴", "RO / ROMANIA"),
    "ROMANIA": ("🇷🇴", "RO / ROMANIA"),
    "RU": ("🇷🇺", "RU / RUSSIA"),
    "RUSSIA": ("🇷🇺", "RU / RUSSIA"),
    "RS": ("🇷🇸", "RS / SERBIA"),
    "SERBIA": ("🇷🇸", "RS / SERBIA"),
    "AZ": ("🇦🇿", "AZ / AZERBAIJAN"),
    "AZERBAIJAN": ("🇦🇿", "AZ / AZERBAIJAN"),
    "IR": ("🇮🇷", "IR / IRAN"),
    "IRAN": ("🇮🇷", "IR / IRAN"),
    "IQ": ("🇮🇶", "IQ / IRAQ"),
    "IRAQ": ("🇮🇶", "IQ / IRAQ"),
    "SE": ("🇸🇪", "SE / SWEDEN"),
    "SWEDEN": ("🇸🇪", "SE / SWEDEN"),
    "NO": ("🇳🇴", "NO / NORWAY"),
    "NORWAY": ("🇳🇴", "NO / NORWAY"),
    "DK": ("🇩🇰", "DK / DENMARK"),
    "DANMARK": ("🇩🇰", "DK / DENMARK"),
    "DENMARK": ("🇩🇰", "DK / DENMARK"),
    "FI": ("🇫🇮", "FI / FINLAND"),
    "FINLAND": ("🇫🇮", "FI / FINLAND"),
    "BE": ("🇧🇪", "BE / BELGIUM"),
    "BELGIQUE": ("🇧🇪", "BE / BELGIUM"),
    "BELGIUM": ("🇧🇪", "BE / BELGIUM"),
    "AT": ("🇦🇹", "AT / AUSTRIA"),
    "AUSTRIA": ("🇦🇹", "AT / AUSTRIA"),
    "CH": ("🇨🇭", "CH / SWITZERLAND"),
    "SWITZERLAND": ("🇨🇭", "CH / SWITZERLAND"),
    "BR": ("🇧🇷", "BR / BRASIL"),
    "BRASIL": ("🇧🇷", "BR / BRASIL"),
    "BRAZIL": ("🇧🇷", "BR / BRASIL"),
    "CA": ("🇨🇦", "CA / CANADA"),
    "CANADA": ("🇨🇦", "CA / CANADA"),
    "AU": ("🇦🇺", "AU / AUSTRALIA"),
    "AUSTRALIA": ("🇦🇺", "AU / AUSTRALIA"),
    "AFRICA": ("🌍", "AFRICA"),
    "AFGANISTAN": ("🇦🇫", "AF / AFGHANISTAN"),
    "ALGERIA": ("🇩🇿", "DZ / ALGERIA"),
    "ARGENTINA": ("🇦🇷", "AR / ARGENTINA"),
    "CHILE": ("🇨🇱", "CL / CHILE"),
    "COLOMBIA": ("🇨🇴", "CO / COLOMBIA"),
    "EGYPT": ("🇪🇬", "EG / EGYPT"),
    "EMIRATES": ("🇦🇪", "AE / EMIRATES"),
    "IRELAND": ("🇮🇪", "IE / IRELAND"),
    "KURDISH": ("☀️", "KURDISH"),
    "LEBANON": ("🇱🇧", "LB / LEBANON"),
    "LIBYA": ("🇱🇾", "LY / LIBYA"),
    "MACEDONIA": ("🇲🇰", "MK / MACEDONIA"),
    "MALTA": ("🇲🇹", "MT / MALTA"),
    "MONTENEGRO": ("🇲🇪", "ME / MONTENEGRO"),
    "MOROCCO": ("🇲🇦", "MA / MOROCCO"),
    "PAKISTAN": ("🇵🇰", "PK / PAKISTAN"),
    "PERU": ("🇵🇪", "PE / PERU"),
    "SAUDIA": ("🇸🇦", "SA / SAUDI ARABIA"),
    "SENEGAL": ("🇸🇳", "SN / SENEGAL"),
    "SLOVAKIA": ("🇸🇰", "SK / SLOVAKIA"),
    "SOMALIA": ("🇸🇴", "SO / SOMALIA"),
    "SUDAN": ("🇸🇩", "SD / SUDAN"),
    "SYRIA": ("🇸🇾", "SY / SYRIA"),
    "TUNISIA": ("🇹🇳", "TN / TUNISIA"),
    "URUGUAY": ("🇺🇾", "UY / URUGUAY"),
    "ADULT": ("🔞", "ADULT / +18"),
    "XXX": ("🔞", "ADULT / +18"),
}


def detect_category_group(name: str) -> str:
    """Kategori adından üst başlığı (ülke / dil / grup) tespit eder.
    
    Örnekler:
      'Deutschland / National' -> '🇩🇪 DE / DEUTSCHLAND'
      'DE/FILM ► Action'        -> '🇩🇪 DE / DEUTSCHLAND'
      'DE ➤ Netflix'           -> '🇩🇪 DE / DEUTSCHLAND'
      'FRANCE / SPORT'          -> '🇫🇷 FR / FRANCE'
      'TR ➤ Guncel Diziler'    -> '🇹🇷 TR / TÜRKİYE'
      'TR/FILM ► Aksiyon'       -> '🇹🇷 TR / TÜRKİYE'
    """
    if not name:
        return "📁 DİĞER / GENEL"
    
    raw = name.strip()

    # 0. Yetişkin içerik kontrolü
    if re.search(r"\b(adult|xxx|\+18|for adult)\b", raw, re.I):
        return "🔞 ADULT / +18"

    # 1. Desen: DE/FILM ►, TR/FILM ►, XX/FILM ►
    m = re.match(r"^([A-Za-z0-9\-_]+)[\/|_]FILM\s*►", raw, re.I)
    if m:
        code = m.group(1).upper()
        if code in COUNTRY_MAP:
            flag, label = COUNTRY_MAP[code]
            return f"{flag} {label}"
        return f"📁 {code}"

    # 2. Desen: DE ➤, TR ➤, DE : ..., TR | ...
    m = re.match(r"^([A-Za-z0-9\-_]+)\s*[➤►:]\s*", raw)
    if m:
        code = m.group(1).upper()
        if code in COUNTRY_MAP:
            flag, label = COUNTRY_MAP[code]
            return f"{flag} {label}"
        return f"📁 {code}"

    # 3. Desen: Turkiye / ..., Deutschland / ..., SOUTH AMERICA (OTHERS) / ...
    m = re.match(r"^([A-Za-z0-9ığüşöçİĞÜŞÖÇ\s\-_()]+?)\s*[/|]\s*", raw)
    if m:
        prefix = m.group(1).strip().upper()
        if prefix in COUNTRY_MAP:
            flag, label = COUNTRY_MAP[prefix]
            return f"{flag} {label}"
        clean = re.sub(r"[^A-Z]", "", prefix)
        if clean in COUNTRY_MAP:
            flag, label = COUNTRY_MAP[clean]
            return f"{flag} {label}"
        return f"📁 {prefix.title()}"

    # 4. Türkçe anahtar kelimeler: 'Sinema', 'Yesilcam', 'Yerli', 'Turk Studio'
    if any(k in raw.lower() for k in ("sinema", "yesilcam", "yerli", "turk studio")):
        return "🇹🇷 TR / TÜRKİYE"

    return "📁 DİĞER / GENEL"


def build_category_groups(categories: list[Any]) -> list[dict]:
    """Kategori listesini üst başlıklarına (parent_name) göre gruplar.
    Her grup için toplam adet, aktif adet ve DOM uyumlu slug anahtar üretir.
    """
    groups_dict: Dict[str, dict] = {}

    for cat in categories:
        grp_name = cat.parent_name or detect_category_group(cat.name)
        if grp_name not in groups_dict:
            # HTML element ID'leri için güvenli slug üret
            safe_key = re.sub(r"[^a-zA-Z0-9]", "_", grp_name).strip("_")
            groups_dict[grp_name] = {
                "name": grp_name,
                "key": safe_key,
                "total_count": 0,
                "enabled_count": 0,
                "categories": [],
            }

        grp = groups_dict[grp_name]
        grp["total_count"] += 1
        if cat.enabled:
            grp["enabled_count"] += 1
        grp["categories"].append(cat)

    # Grupları mantıksal sıraya koy (TR en başta, sonra DE, FR, vb., Diğer ve Adult sonda)
    def group_sort_order(g: dict) -> Tuple[int, str]:
        name = g["name"]
        if "TR /" in name or "TÜRKİYE" in name:
            return (0, name)
        if "DE /" in name or "DEUTSCHLAND" in name:
            return (1, name)
        if "FR /" in name or "FRANCE" in name:
            return (2, name)
        if "UK /" in name or "USA /" in name:
            return (3, name)
        if "NL /" in name or "IT /" in name or "ES /" in name:
            return (4, name)
        if "ADULT" in name:
            return (99, name)
        if "DİĞER" in name:
            return (98, name)
        return (10, name)

    return sorted(groups_dict.values(), key=group_sort_order)


def backfill_category_parents(db: Session) -> int:
    """Veritabanındaki kategorilerin parent_name sütununu günceller."""
    from .models import Category

    cats = db.query(Category).all()
    count = 0
    for cat in cats:
        expected = detect_category_group(cat.name)
        if cat.parent_name != expected:
            cat.parent_name = expected
            count += 1

    if count > 0:
        db.commit()
    return count
