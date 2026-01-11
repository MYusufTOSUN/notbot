"""
Telegram Bildirim Modülü
Not değişikliklerini Telegram üzerinden kullanıcıya bildirir.
"""

import asyncio
from typing import Dict, List, Optional
from telegram import Bot
from telegram.error import TelegramError
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from src.logger import log_info, log_error, log_success


class TelegramNotifier:
    """Telegram bildirimleri gönderen sınıf."""
    
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = token
        self.chat_id = chat_id
        self.bot: Optional[Bot] = None
        
        if self.token and self.chat_id:
            self.bot = Bot(token=self.token)
    
    async def send_message(self, message: str) -> bool:
        """
        Telegram mesajı gönder.
        
        Args:
            message: Gönderilecek mesaj
            
        Returns:
            Başarılı ise True
        """
        if not self.bot:
            log_error("Telegram bot yapılandırılmamış!")
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode="HTML"
            )
            log_success(f"Telegram mesajı gönderildi: {message[:50]}...")
            return True
            
        except TelegramError as e:
            log_error(f"Telegram gönderim hatası: {e}")
            return False
    
    async def send_grade_notification(self, course_name: str, new_grade: str, 
                                       old_grade: Optional[str] = None) -> bool:
        """
        Not bildirimi gönder.
        
        Args:
            course_name: Ders adı
            new_grade: Yeni not
            old_grade: Eski not (opsiyonel)
        """
        if old_grade:
            message = (
                f"🔔 <b>NOT GÜNCELLEMESİ!</b>\n\n"
                f"📚 <b>Ders:</b> {course_name}\n"
                f"📊 <b>Eski Not:</b> {old_grade}\n"
                f"✨ <b>Yeni Not:</b> {new_grade}\n\n"
                f"🎓 ÖBS Botunuz sizin için çalışıyor!"
            )
        else:
            message = (
                f"🔔 <b>NOT ALARMI!</b>\n\n"
                f"📚 <b>Ders:</b> {course_name}\n"
                f"✨ <b>Yeni Not:</b> {new_grade}\n\n"
                f"🎉 Notunuz açıklandı!"
            )
        
        return await self.send_message(message)
    
    async def send_multiple_grade_notifications(self, changes: List[Dict]) -> int:
        """
        Birden fazla not değişikliği bildirimi gönder.
        Basit format: DERS ADI: XX (not türü)
        """
        if not changes:
            return 0
        
        # Alan adlarını Türkçeleştir
        field_names = {
            "vize1": "Vize1",
            "vize2": "Vize2", 
            "vize3": "Vize3",
            "vize4": "Vize4",
            "final": "Final",
            "but": "Büt",
            "gn": "GN",
            "harf": "Harf",
            "durum": "Durum",
            "yeni_ders": "Yeni"
        }
        
        success_count = 0
        
        # Tüm değişiklikleri tek bir mesajda gönder
        message = "🔔 <b>NOT GÜNCELLEMESİ</b>\n\n"
        
        for change in changes:
            course = change.get("course", "Bilinmeyen Ders")
            field = change.get("field", "not")
            new_value = change.get("new_value", "-")
            
            field_display = field_names.get(field, field)
            
            # Basit format: DERS ADI: XX (not türü)
            message += f"📚 {course}: <b>{new_value}</b> ({field_display})\n"
        
        message += "\n🎓 ÖBS Bot"
        
        if await self.send_message(message):
            success_count = len(changes)
        
        log_info(f"{success_count}/{len(changes)} bildirim gönderildi")
        return success_count
    
    async def send_startup_notification(self) -> bool:
        """Bot başlatma bildirimi gönder."""
        message = (
            "🚀 <b>ÖBS Bot Aktif!</b>\n\n"
            "✅ Bot başarıyla başlatıldı\n"
            "🔄 Notlarınız kontrol ediliyor...\n\n"
            "📱 Yeni not açıklandığında bildirim alacaksınız."
        )
        return await self.send_message(message)
    
    async def send_error_notification(self, error_type: str, details: str) -> bool:
        """Hata bildirimi gönder."""
        message = (
            f"⚠️ <b>ÖBS Bot Hatası</b>\n\n"
            f"❌ <b>Hata Türü:</b> {error_type}\n"
            f"📝 <b>Detay:</b> {details}\n\n"
            f"🔧 Lütfen logları kontrol edin."
        )
        return await self.send_message(message)
    
    async def send_no_changes_notification(self) -> bool:
        """Değişiklik yok bildirimi (debug amaçlı)."""
        message = (
            "✅ <b>ÖBS Kontrol Tamamlandı</b>\n\n"
            "📊 Notlarınızda değişiklik yok.\n"
            "🔄 20 dakika sonra tekrar kontrol edilecek."
        )
        return await self.send_message(message)


def sync_send_notification(course_name: str, new_grade: str, 
                           old_grade: Optional[str] = None) -> bool:
    """Senkron bildirim gönderme fonksiyonu."""
    notifier = TelegramNotifier()
    return asyncio.run(notifier.send_grade_notification(course_name, new_grade, old_grade))


def sync_send_multiple_notifications(changes: List[Dict]) -> int:
    """Senkron çoklu bildirim gönderme fonksiyonu."""
    notifier = TelegramNotifier()
    return asyncio.run(notifier.send_multiple_grade_notifications(changes))
