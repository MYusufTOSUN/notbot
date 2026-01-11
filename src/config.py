"""
Yapılandırma Modülü
Tüm bot ayarlarını ve environment değişkenlerini yönetir.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

# Proje kök dizini
PROJECT_ROOT = Path(__file__).parent.parent

# ÖBS Yapılandırması
OBS_URL = os.getenv("OBS_URL", "https://obis1.selcuk.edu.tr")
OBS_USERNAME = os.getenv("OBS_USER", "")  # GitHub Secret: OBS_USER
OBS_PASSWORD = os.getenv("OBS_PASS", "")  # GitHub Secret: OBS_PASS

# Telegram Yapılandırması
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "")  # GitHub Secret: TELEGRAM_TOKEN
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# JSONBin.io Yapılandırması (Opsiyonel)
JSONBIN_API_KEY = os.getenv("JSONBIN_KEY", "")  # GitHub Secret: JSONBIN_KEY
JSONBIN_BIN_ID = os.getenv("JSONBIN_ID", "")  # GitHub Secret: JSONBIN_ID

# GitHub Yapılandırması (Opsiyonel)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# Dosya Yolları
GRADES_FILE = PROJECT_ROOT / "notlar.json"
LOGS_FILE = PROJECT_ROOT / "logs.txt"

# OCR Yapılandırması
OCR_CONFIG = {
    "lang": "eng",
    "config": "--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789",
    "max_retries": 5,
    "timeout": 30
}

# Playwright Yapılandırması
BROWSER_CONFIG = {
    "headless": True,
    "slow_mo": 100,  # İşlemler arası bekleme (ms)
    "timeout": 60000,  # Sayfa yükleme timeout (ms)
    "viewport": {"width": 1920, "height": 1080}
}

# Retry Yapılandırması
RETRY_CONFIG = {
    "max_attempts": 5,
    "delay_between_attempts": 2,  # saniye
    "captcha_retry_delay": 1  # saniye
}


def validate_config():
    """Kritik yapılandırma değerlerini doğrula."""
    errors = []
    
    if not OBS_USERNAME:
        errors.append("OBS_USERNAME tanımlanmamış!")
    if not OBS_PASSWORD:
        errors.append("OBS_PASSWORD tanımlanmamış!")
    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN tanımlanmamış!")
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID tanımlanmamış!")
    
    return errors


def get_storage_mode():
    """
    Hangi depolama modunun kullanılacağını belirle.
    Öncelik: JSONBin > GitHub > Lokal
    """
    if JSONBIN_API_KEY and JSONBIN_BIN_ID:
        return "jsonbin"
    elif GITHUB_TOKEN and GITHUB_REPO:
        return "github"
    else:
        return "local"
