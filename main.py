#!/usr/bin/env python3
"""
ÖBS Push Bot - Ana Giriş Noktası
Bu dosya botu başlatır ve tüm akışı yönetir.
"""
import asyncio
import sys
from src.config import validate_config
from src.bot import run_bot
from src.data_manager import DataManager
from src.telegram_notifier import TelegramNotifier
from src.logger import log_info, log_error, log_success


async def main():
    log_info("="*50)
    log_info("ÖBS Push Bot Başlatılıyor...")
    
    # Yapılandırma kontrolü
    errors = validate_config()
    if errors:
        for e in errors:
            log_error(e)
        sys.exit(1)
    
    notifier = TelegramNotifier()
    data_manager = DataManager()
    
    try:
        # Eski notları yükle
        old_grades = data_manager.load_grades()
        log_info(f"Kayıtlı {len(old_grades)} ders bulundu")
        
        # Bot'u çalıştır
        success, new_grades = await run_bot()
        
        if not success:
            log_error("ÖBS girişi başarısız!")
            await notifier.send_error_notification("Login Hatası", "ÖBS'ye giriş yapılamadı")
            sys.exit(1)
        
        if not new_grades:
            log_info("Henüz not yok")
            sys.exit(0)
        
        # Değişiklikleri tespit et
        changes = data_manager.compare_grades(old_grades, new_grades)
        
        if changes:
            log_success(f"{len(changes)} not değişikliği tespit edildi!")
            await notifier.send_multiple_grade_notifications(changes)
            data_manager.save_grades(new_grades)
        else:
            log_info("Notlarda değişiklik yok")
        
        log_success("Bot başarıyla tamamlandı!")
        
    except Exception as e:
        log_error(f"Kritik hata: {e}")
        await notifier.send_error_notification("Kritik Hata", str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
