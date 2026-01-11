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
    
    async def _solve_captcha(self) -> bool:
        """Selçuk ÖBS captcha çözücü - Gelişmiş Strateji"""
        try:
            captcha_text = None
            captcha_element = await self.page.query_selector('img#Image1')
            
            if captcha_element:
                # 1. img etiketinin title veya alt özelliği
                title_text = await captcha_element.get_attribute('title')
                alt_text = await captcha_element.get_attribute('alt')
                
                if title_text and title_text.isdigit() and len(title_text) == 4:
                    captcha_text = title_text
                    log_info(f"Captcha HTML'den alındı (img title): {captcha_text}")
                elif alt_text and alt_text.isdigit() and len(alt_text) == 4:
                    captcha_text = alt_text
                    log_info(f"Captcha HTML'den alındı (img alt): {captcha_text}")
                
                # 2. img etiketinin ebeveyninin (parent) title özelliği (Tooltip genelde burada olur)
                if not captcha_text:
                    parent_element = await captcha_element.query_selector('..')
                    if parent_element:
                        parent_title = await parent_element.get_attribute('title')
                        if parent_title and parent_title.isdigit() and len(parent_title) == 4:
                            captcha_text = parent_title
                            log_info(f"Captcha HTML'den alındı (parent title): {captcha_text}")
                        
                        # Parent'ın text içeriği
                        parent_text = await parent_element.inner_text()
                        if parent_text:
                            import re
                            matches = re.findall(r'\b(\d{4})\b', parent_text)
                            if matches:
                                captcha_text = matches[0]
                                log_info(f"Captcha HTML'den alındı (parent text): {captcha_text}")

            # 3. Gizli input kontrolü
            if not captcha_text:
                hidden_inputs = await self.page.query_selector_all('input[type="hidden"]')
                for inp in hidden_inputs:
                    value = await inp.get_attribute('value')
                    if value and value.isdigit() and len(value) == 4:
                        captcha_text = value
                        log_info(f"Captcha hidden input'tan alındı: {captcha_text}")
                        break
            
            # 4. URL Parametresi
            if not captcha_text and captcha_element:
                src = await captcha_element.get_attribute('src')
                if src and 'text=' in src.lower():
                    import re
                    match = re.search(r'text=(\d+)', src, re.IGNORECASE)
                    if match:
                        captcha_text = match.group(1)
                        log_info(f"Captcha URL'den alındı: {captcha_text}")
            
            # 5. Sayfa Kaynağında Regex Arama
            if not captcha_text:
                page_content = await self.page.content()
                import re
                # "7000" gibi tooltip değerleri bazen script içinde olur
                matches = re.findall(r'Tooltip\s*\(.*["\'](\d{4})["\']', page_content, re.IGNORECASE)
                if matches:
                    captcha_text = matches[0]
                    log_info(f"Captcha script içinden alındı: {captcha_text}")

            # 6. Son çare - OCR
            if not captcha_text and captcha_element:
                log_debug("HTML'de captcha bulunamadı, OCR deneniyor...")
                # Windows için Tesseract yolunu kontrol et (Lokal çalışma için)
                import shutil
                if not shutil.which("tesseract"):
                    # Yaygın Windows yolları
                    common_paths = [
                        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                        r"C:\Users\tosun\AppData\Local\Tesseract-OCR\tesseract.exe"
                    ]
                    for path in common_paths:
                        if os.path.exists(path):
                            pytesseract.pytesseract.tesseract_cmd = path
                            log_debug(f"Tesseract yolu ayarlandı: {path}")
                            break

                screenshot_bytes = await captcha_element.screenshot()
                captcha_text = self.ocr_handler.extract_with_retry(screenshot_bytes, expected_length=4)
                if captcha_text:
                    log_info(f"Captcha OCR ile çözüldü: {captcha_text}")
            
            if not captcha_text:
                log_warning("Captcha çözülemedi!")
                return False
            
            # Captcha input alanına yaz
            await self.page.fill('input#TxtCaptcha', captcha_text)
            log_debug(f"Captcha kodu girildi: {captcha_text}")
            
            return True
            
        except Exception as e:
            log_error(f"Captcha çözme hatası: {e}")
            return False
    
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
