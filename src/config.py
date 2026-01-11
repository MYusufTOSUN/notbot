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
OBS_URL = os.getenv("OBS_URL", "https://obis1.selcuk.edu.tr").strip()
OBS_USERNAME = os.getenv("OBS_USER", "").strip()
OBS_PASSWORD = os.getenv("OBS_PASS", "").strip()

# Telegram Yapılandırması
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# JSONBin.io Yapılandırması (Opsiyonel)
JSONBIN_API_KEY = os.getenv("JSONBIN_KEY", "").strip()
JSONBIN_BIN_ID = os.getenv("JSONBIN_ID", "").strip()

# GitHub Yapılandırması (Opsiyonel)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")

# Dosya Yolları
GRADES_FILE = PROJECT_ROOT / "notlar.json"
LOGS_FILE = PROJECT_ROOT / "logs.txt"

# OCR Yapılandırması (EasyOCR + OpenCV)
OCR_CONFIG = {
    "strategies": 7,  # Kullanılan strateji sayısı
    "expected_length": 4,  # Beklenen captcha uzunluğu
    "debug_mode": True,  # Debug görsellerini kaydet
    "resize_scale": 2.0,  # Görüntü büyütme oranı
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
    "max_attempts": 7,  # OCR stratejileri ile daha fazla şans
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
