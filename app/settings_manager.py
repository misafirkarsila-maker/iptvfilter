"""Ayarlar ve Güvenlik Yöneticisi — ENCRYPTION_KEY, API ve Panel Şifreleri.

Bu modül:
1. ENCRYPTION_KEY boşsa otomatik üretir ve data/.encryption_key ile .env'e yazar.
2. API_USER (varsayılan: myuser) ve API_PASSWORD (otomatik 10 haneli güvenli şifre) yönetir.
3. İlk kurulumda web arayüzünden (/setup) panel şifresi belirleme veya şifresiz kullanım sağlar.
4. Ayarları data/settings.json içinde kalıcı tutar (Docker container yeniden başlasa da kaybolmaz).
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
SETTINGS_FILE = DATA_DIR / "settings.json"
KEY_FILE = DATA_DIR / ".encryption_key"
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE_FILE = BASE_DIR / ".env.example"

_CACHE: Dict[str, Any] = {}


def generate_secure_password(length: int = 6) -> str:
    """TV kumandasıyla kolayca girilebilmesi için sadece rakamlardan oluşan sayısal PIN şifre üretir."""
    first_digit = secrets.choice("123456789")
    remaining_digits = "".join(secrets.choice("0123456789") for _ in range(length - 1))
    return first_digit + remaining_digits


def update_env_file(updates: Dict[str, str]) -> None:
    """Mevcut .env dosyasına anahtar-değer çiftlerini yazar veya günceller."""
    try:
        if not ENV_FILE.exists():
            if ENV_EXAMPLE_FILE.exists():
                content = ENV_EXAMPLE_FILE.read_text(encoding="utf-8")
            else:
                content = ""
        else:
            content = ENV_FILE.read_text(encoding="utf-8")

        for key, val in updates.items():
            val_str = str(val) if val is not None else ""
            pattern = rf"^(#\s*)?({re.escape(key)}=.*)$"
            replacement = f"{key}={val_str}"
            if re.search(pattern, content, flags=re.MULTILINE):
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                if content and not content.endswith("\n"):
                    content += "\n"
                content += f"{key}={val_str}\n"

        ENV_FILE.write_text(content, encoding="utf-8")
        try:
            os.chmod(ENV_FILE, 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f".env dosyası güncellenemedi: {e}")


def load_settings() -> Dict[str, Any]:
    """data/settings.json dosyasından ayarları okur."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"settings.json okunamadı: {e}")
    return {}


def save_settings(settings: Dict[str, Any]) -> None:
    """Ayarları data/settings.json içine atomik olarak kaydeder."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = SETTINGS_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temp_file.replace(SETTINGS_FILE)
    _CACHE.clear()
    _CACHE.update(settings)


def init_security_settings() -> Dict[str, Any]:
    """
    Uygulama başlarken ENCRYPTION_KEY, API_USER, API_PASSWORD ve PANEL_PASSWORD
    değerlerini yükler, eksik olanları otomatik üretip kalıcı depolar.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings = load_settings()
    env_updates: Dict[str, str] = {}
    dirty = False

    # 1. ENCRYPTION_KEY
    # Öncelik: os.getenv > KEY_FILE > settings.json > yeni üret
    enc_key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not enc_key and KEY_FILE.exists():
        try:
            key_from_file = KEY_FILE.read_text(encoding="utf-8").strip()
            if key_from_file:
                enc_key = key_from_file
        except Exception:
            pass

    if not enc_key and settings.get("encryption_key"):
        enc_key = settings["encryption_key"].strip()

    if not enc_key:
        # Otomatik Fernet anahtarı üret
        enc_key = Fernet.generate_key().decode()
        logger.info("Yeni ENCRYPTION_KEY otomatik olarak üretildi.")

    # Kalıcı data/.encryption_key dosyasına yaz
    try:
        if not KEY_FILE.exists() or KEY_FILE.read_text(encoding="utf-8").strip() != enc_key:
            KEY_FILE.write_text(enc_key, encoding="utf-8")
    except Exception as e:
        logger.warning(f"{KEY_FILE} dosyasına anahtar yazılamadı: {e}")

    if settings.get("encryption_key") != enc_key:
        settings["encryption_key"] = enc_key
        dirty = True

    if os.getenv("ENCRYPTION_KEY", "").strip() != enc_key:
        env_updates["ENCRYPTION_KEY"] = enc_key

    # 2. API_USER
    env_api_user = os.getenv("API_USER", "").strip()
    api_user = env_api_user or settings.get("api_user") or "myuser"
    if settings.get("api_user") != api_user:
        settings["api_user"] = api_user
        dirty = True

    # 3. API_PASSWORD
    env_api_pass = os.getenv("API_PASSWORD", "").strip()
    if env_api_pass and env_api_pass not in ("changeme", "mypassword"):
        api_password = env_api_pass
    elif settings.get("api_password"):
        api_password = settings["api_password"]
    else:
        # Otomatik güvenli şifre üret
        api_password = generate_secure_password(10)
        env_updates["API_PASSWORD"] = api_password
        logger.info(f"IPTV API için otomatik şifre üretildi: {api_password}")

    if settings.get("api_password") != api_password:
        settings["api_password"] = api_password
        dirty = True

    # 4. PANEL_PASSWORD & KURULUM DURUMU
    env_panel_pass = os.getenv("PANEL_PASSWORD", "").strip()
    if env_panel_pass and env_panel_pass not in ("changeme", ""):
        # Env üzerinden açıkça bir şifre verilmişse kurulumu tamamlanmış say
        settings["panel_password"] = env_panel_pass
        settings["is_setup_done"] = True
        dirty = True
    elif "is_setup_done" not in settings:
        # Yeni kurulum: Kullanıcı ilk girişte web sihirbazına (/setup) yönlendirilecek
        settings["is_setup_done"] = False
        settings["panel_password"] = None
        dirty = True

    if dirty:
        save_settings(settings)

    if env_updates and ENV_FILE.exists():
        update_env_file(env_updates)

    _CACHE.clear()
    _CACHE.update(settings)
    return settings


def _get_active_settings() -> Dict[str, Any]:
    global _CACHE
    if not _CACHE:
        _CACHE = init_security_settings()
    return _CACHE


def is_setup_completed() -> bool:
    """İlk kurulum sihirbazının tamamlanıp tamamlanmadığını döner."""
    return bool(_get_active_settings().get("is_setup_done", False))


def get_encryption_key() -> str:
    """Aktif şifreleme anahtarını döner."""
    return str(_get_active_settings().get("encryption_key", ""))


def get_api_username() -> str:
    """Aktif API kullanıcı adını döner (varsayılan: myuser)."""
    return str(_get_active_settings().get("api_user", "myuser"))


def get_api_password() -> str:
    """Aktif API şifresini döner."""
    return str(_get_active_settings().get("api_password", ""))


def get_panel_password() -> Optional[str]:
    """Aktif panel şifresini döner (şifresiz ise None)."""
    return _get_active_settings().get("panel_password") or None


def has_panel_password() -> bool:
    """Panelin bir şifreyle korunup korunmadığını döner."""
    return bool(get_panel_password())


def complete_setup(panel_password: Optional[str] = None) -> None:
    """İlk kurulum sihirbazını tamamlar ve ayarları kaydeder."""
    settings = load_settings()
    cleaned_pass = panel_password.strip() if panel_password else None
    settings["panel_password"] = cleaned_pass
    settings["is_setup_done"] = True
    save_settings(settings)
    if ENV_FILE.exists():
        update_env_file({"PANEL_PASSWORD": cleaned_pass or ""})


def set_panel_password(panel_password: Optional[str]) -> None:
    """Panel şifresini günceller veya kaldırır (şifresiz moda alır)."""
    settings = load_settings()
    cleaned_pass = panel_password.strip() if panel_password else None
    settings["panel_password"] = cleaned_pass
    save_settings(settings)
    if ENV_FILE.exists():
        update_env_file({"PANEL_PASSWORD": cleaned_pass or ""})


def set_api_password(new_password: str) -> str:
    """API şifresini günceller ve kaydeder."""
    clean_pass = str(new_password).strip()
    settings = load_settings()
    settings["api_password"] = clean_pass
    save_settings(settings)
    if ENV_FILE.exists():
        update_env_file({"API_PASSWORD": clean_pass})
    return clean_pass


def regenerate_api_password(length: int = 6) -> str:
    """Yeni bir sayısal API şifresi (PIN) üretir ve kaydeder."""
    new_pass = generate_secure_password(length)
    settings = load_settings()
    settings["api_password"] = new_pass
    save_settings(settings)
    if ENV_FILE.exists():
        update_env_file({"API_PASSWORD": new_pass})
    return new_pass


def is_stream_proxy_enabled() -> bool:
    """Video akışlarının sunucu üzerinden proxy edilip edilmeyeceğini döner (varsayılan: False)."""
    return bool(_get_active_settings().get("stream_proxy_enabled", False))


def set_stream_proxy_enabled(enabled: bool) -> None:
    """Video proxy modunu açar veya kapatır."""
    settings = load_settings()
    settings["stream_proxy_enabled"] = bool(enabled)
    save_settings(settings)

