#!/usr/bin/env python3
"""
ÖBS Push Bot - Ana Giriş Noktası
Bu dosya botu başlatır ve tüm akışı yönetir.
"""
import asyncio
import sys
from datetime import datetime
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
    
    # Sonuç bilgisi için değişkenler
    result_status = "❓ Bilinmiyor"
    result_details = ""
    grades_count = 0
    changes_count = 0
    
    try:
        # Eski notları yükle
        old_grades = data_manager.load_grades()
        log_info(f"Kayıtlı {len(old_grades)} ders bulundu")
        
        # Bot'u çalıştır
        success, new_grades = await run_bot()
        
        if not success:
            log_error("ÖBS girişi başarısız!")
            result_status = "❌ Giriş Başarısız"
            result_details = "ÖBS'ye giriş yapılamadı. Site erişilemez veya captcha çözülemedi."
        else:
            grades_count = len(new_grades)
            
            if not new_grades:
                log_info("Henüz not yok")
                result_status = "✅ Çalıştı"
                result_details = "Giriş başarılı, ancak henüz açıklanmış not bulunamadı."
            else:
                # Değişiklikleri tespit et
                changes = data_manager.compare_grades(old_grades, new_grades)
                changes_count = len(changes)
                
                if changes:
                    log_success(f"{len(changes)} not değişikliği tespit edildi!")
                    await notifier.send_multiple_grade_notifications(changes)
                    data_manager.save_grades(new_grades)
                    result_status = "🎉 Yeni Not!"
                    result_details = f"{changes_count} adet not değişikliği tespit edildi ve bildirildi."
                else:
                    log_info("Notlarda değişiklik yok")
                    result_status = "✅ Çalıştı"
                    result_details = f"{grades_count} ders kontrol edildi, değişiklik yok."
        
        log_success("Bot başarıyla tamamlandı!")
        
    except Exception as e:
        log_error(f"Kritik hata: {e}")
        result_status = "💥 Kritik Hata"
        result_details = str(e)
    
    finally:
        # Her durumda özet bildirim gönder
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        summary_message = (
            f"📊 <b>ÖBS Bot Raporu</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🕐 <b>Zaman:</b> {now}\n"
            f"📌 <b>Durum:</b> {result_status}\n\n"
            f"📝 <b>Detay:</b>\n{result_details}\n\n"
            f"📚 <b>Kontrol Edilen:</b> {grades_count} ders\n"
            f"🔔 <b>Değişiklik:</b> {changes_count} adet\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <i>Sonraki kontrol 20 dk sonra</i>"
        )
        
        try:
            await notifier.send_message(summary_message)
            log_success("Özet bildirim gönderildi")
        except Exception as e:
            log_error(f"Özet bildirim gönderilemedi: {e}")


if __name__ == "__main__":
    asyncio.run(main())
