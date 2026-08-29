import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Veritabanı
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}"
)

# Sunucu
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))

# Kendi Xtream API / Panel kimlik doğrulaması & Şifreleme
from . import settings_manager

def reload_security_config():
    global API_USERNAME, API_PASSWORD, PANEL_PASSWORD, ENCRYPTION_KEY
    API_USERNAME = settings_manager.get_api_username()
    API_PASSWORD = settings_manager.get_api_password()
    PANEL_PASSWORD = settings_manager.get_panel_password()
    ENCRYPTION_KEY = settings_manager.get_encryption_key()

settings_manager.init_security_settings()
API_USERNAME = settings_manager.get_api_username()
API_PASSWORD = settings_manager.get_api_password()
PANEL_PASSWORD = settings_manager.get_panel_password()
ENCRYPTION_KEY = settings_manager.get_encryption_key()

# Senkronizasyon cron
SYNC_CRON = os.getenv("SYNC_CRON", "0 3 * * *")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

