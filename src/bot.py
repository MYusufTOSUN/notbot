"""
Ana Bot Modülü - Selçuk Üniversitesi ÖBS (OBİS) için özelleştirilmiş
Playwright ile giriş yapar, captcha çözer ve notları çeker.
"""
import asyncio
from typing import Dict, Optional, Tuple
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from src.config import OBS_URL, OBS_USERNAME, OBS_PASSWORD, BROWSER_CONFIG, RETRY_CONFIG
from src.ocr_handler import OCRHandler
from src.logger import log_info, log_error, log_debug, log_success, log_warning


class OBSBot:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.ocr_handler = OCRHandler()
        
        # Selçuk Üniversitesi OBİS URL'leri
        self.login_url = OBS_URL
        self.grades_url = f"{OBS_URL}/Ogrenci/SonYilNotlari"
        
    async def start(self):
        log_info("Tarayıcı başlatılıyor...")
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=BROWSER_CONFIG["headless"],
            slow_mo=BROWSER_CONFIG["slow_mo"]
        )
        self.context = await self.browser.new_context(
            viewport=BROWSER_CONFIG["viewport"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        )
        self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_CONFIG["timeout"])
        log_success("Tarayıcı başlatıldı")
    
    async def stop(self):
        try:
            if self.page: await self.page.close()
            if self.context: await self.context.close()
            if self.browser: await self.browser.close()
            if self._playwright: await self._playwright.stop()
            self.ocr_handler.cleanup()
            log_info("Tarayıcı kapatıldı")
        except Exception as e:
            log_error(f"Tarayıcı kapatma hatası: {e}")
    
    async def login(self) -> Tuple[bool, str]:
        max_attempts = RETRY_CONFIG["max_attempts"]
        last_error = ""
        
        for attempt in range(1, max_attempts + 1):
            try:
                log_info(f"Giriş denemesi {attempt}/{max_attempts}")
                await self.page.goto(self.login_url, wait_until="networkidle")
                log_debug("Login sayfası yüklendi")
                
                # Selçuk ÖBS Form Alanları
                await self.page.fill('input[name="id"]', OBS_USERNAME)
                log_debug("Öğrenci numarası girildi")
                
                await self.page.fill('input[name="pass"]', OBS_PASSWORD)
                log_debug("Şifre girildi")
                
                # Captcha çöz
                if not await self._solve_captcha():
                    last_error = "Captcha çözülemedi"
                    log_warning(f"{last_error}, sayfa yenileniyor...")
                    await asyncio.sleep(1)
                    continue
                
                # Giriş butonuna tıkla
                await self.page.click('button.btn-login')
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                # Giriş başarılı mı kontrol et
                is_success, error_msg = await self._check_login_success()
                if is_success:
                    log_success("Giriş başarılı!")
                    return True, ""
                else:
                    last_error = error_msg or "Giriş başarısız (bilgiler yanlış olabilir)"
                    log_warning(f"{last_error} - captcha yanlış olabilir")
                    
            except Exception as e:
                last_error = str(e)
                log_error(f"Giriş hatası: {e}")
            
            await asyncio.sleep(RETRY_CONFIG["delay_between_attempts"])
        
        log_error(f"Giriş {max_attempts} denemeden sonra başarısız!")
        return False, last_error
    
    async def _check_login_success(self) -> Tuple[bool, str]:
        """Giriş başarılı mı kontrol et - Sayfa içeriğine bakarak"""
        try:
            page_content = await self.page.content()
            page_content_lower = page_content.lower()
            
            # Site hata kontrolü
            error_indicators = [
                'hata oluştu', 'sunucu hatası', 'erişilemiyor',
                'service unavailable', '503', '502', '500'
            ]
            for indicator in error_indicators:
                if indicator in page_content_lower:
                    msg = f"Site hatası: {indicator}"
                    log_warning(msg)
                    return False, msg
            
            # Hala login sayfasındaysa başarısız
            if 'txtcaptcha' in page_content_lower or 'btn-login' in page_content_lower:
                error_el = await self.page.query_selector('.alert-danger, .alert-warning')
                if error_el:
                    error_text = await error_el.inner_text()
                    msg = f"Hata mesajı: {error_text}"
                    log_warning(msg)
                    return False, msg
                return False, "Hala login sayfasında"
            
            # Başarılı giriş göstergeleri
            success_indicators = ['anasayfa', 'çıkış', 'cikis', 'logout', 'son yıl notları', 'not durumu']
            for indicator in success_indicators:
                if indicator in page_content_lower:
                    log_debug(f"Giriş başarılı - gösterge: {indicator}")
                    return True, ""
            
            msg = "Giriş göstergesi bulunamadı"
            log_warning(msg)
            return False, msg
            
        except Exception as e:
            msg = f"Giriş kontrolü hatası: {e}"
            log_error(msg)
            return False, msg

    async def run(self) -> Tuple[bool, Dict, str]:
        try:
            await self.start()
            is_login, login_error = await self.login()
            if is_login:
                grades = await self.fetch_grades()
                return (True, grades, "")
            return (False, {}, login_error)
        except Exception as e:
            log_error(f"Bot hatası: {e}")
            return (False, {}, str(e))
        finally:
            await self.stop()


async def run_bot() -> Tuple[bool, Dict, str]:
    bot = OBSBot()
    return await bot.run()
