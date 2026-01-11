"""
Loglama Modülü
Tüm bot aktivitelerini logs.txt dosyasına kaydeder.
"""

import sys
from datetime import datetime
from pathlib import Path
from src.config import LOGS_FILE


class Logger:
    """Merkezi loglama sınıfı."""
    
    def __init__(self, log_file: Path = LOGS_FILE):
        self.log_file = log_file
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Log dosyasının var olduğundan emin ol."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
    
    def _write(self, level: str, message: str):
        """Log mesajını dosyaya ve konsola yaz."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        # Konsola yaz
        print(log_entry.strip())
        
        # Dosyaya yaz
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Log yazma hatası: {e}", file=sys.stderr)
    
    def info(self, message: str):
        """Bilgi seviyesi log."""
        self._write("INFO", message)
    
    def error(self, message: str):
        """Hata seviyesi log."""
        self._write("ERROR", message)
    
    def warning(self, message: str):
        """Uyarı seviyesi log."""
        self._write("WARNING", message)
    
    def debug(self, message: str):
        """Debug seviyesi log."""
        self._write("DEBUG", message)
    
    def success(self, message: str):
        """Başarı seviyesi log."""
        self._write("SUCCESS", message)
    
    def clear(self):
        """Log dosyasını temizle (sadece son 1000 satırı tut)."""
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            if len(lines) > 1000:
                with open(self.log_file, "w", encoding="utf-8") as f:
                    f.writelines(lines[-1000:])
                    
        except Exception as e:
            print(f"Log temizleme hatası: {e}", file=sys.stderr)


# Global logger instance
_logger = Logger()


def log_info(message: str):
    """Global info log fonksiyonu."""
    _logger.info(message)


def log_error(message: str):
    """Global error log fonksiyonu."""
    _logger.error(message)


def log_warning(message: str):
    """Global warning log fonksiyonu."""
    _logger.warning(message)


def log_debug(message: str):
    """Global debug log fonksiyonu."""
    _logger.debug(message)


def log_success(message: str):
    """Global success log fonksiyonu."""
    _logger.success(message)
