#!/usr/bin/env python3
"""
ÖBS Push Bot - Ana Giriş Noktası
Bu dosya botu başlatır ve tüm akışı yönetir.
Sadece not değişikliği olduğunda Telegram bildirimi gönderir.
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
        success, new_grades, error_msg = await run_bot()
        
        if not success:
            log_error(f"ÖBS girişi başarısız: {error_msg}")
            # Giriş başarısız - mesaj gönderme
            return
        
        # Dönem ortalamasını al (meta veri)
        donem_ortalamasi = new_grades.pop("_donem_ortalamasi", "")
        grades_count = len(new_grades)
        
        if not new_grades:
            log_info("Henüz not yok")
            # Not yok - mesaj gönderme
            return
        
        # Değişiklikleri tespit et
        changes = data_manager.compare_grades(old_grades, new_grades)
        
        if changes:
            # SADECE DEĞİŞİKLİK VARSA MESAJ GÖNDER
            log_success(f"{len(changes)} not değişikliği tespit edildi!")
            await notifier.send_multiple_grade_notifications(changes)
            data_manager.save_grades(new_grades)
            log_success("Bildirim gönderildi ve notlar kaydedildi!")
        else:
            log_info(f"Notlarda değişiklik yok ({grades_count} ders kontrol edildi)")
            # Değişiklik yok - mesaj gönderme
        
        log_success("Bot başarıyla tamamlandı!")
        
    except Exception as e:
        log_error(f"Kritik hata: {e}")
        # Hata durumunda da mesaj gönderme


if __name__ == "__main__":
    asyncio.run(main())
