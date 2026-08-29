import base64
import os
import re
from cryptography.fernet import Fernet, InvalidToken
from . import config, settings_manager

_FERNET = None
_FERNET_KEY = None

def _get_fernet() -> Fernet:
    global _FERNET, _FERNET_KEY
    key = settings_manager.get_encryption_key()
    if not key:
        settings_manager.init_security_settings()
        key = settings_manager.get_encryption_key()
    
    if _FERNET and _FERNET_KEY == key:
        return _FERNET
    
    _FERNET = Fernet(key.encode())
    _FERNET_KEY = key
    return _FERNET

def init_encryption_key() -> str:
    """Uygulama başlangıcında şifreleme anahtarını garantiye alır."""
    f = _get_fernet()
    return _FERNET_KEY


def encrypt(plaintext: str) -> str:
    if not plaintext: return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()

def decrypt(token: str) -> str:
    if not token: return ""
    f = _get_fernet()
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Şifre çözülemedi. ENCRYPTION_KEY değişmiş olabilir.")
