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
        self.login_url = OBS_URL  # Ana sayfa = giriş sayfası
        self.grades_url = f"{OBS_URL}/OgrenimBilgileri/NotListesi"
        
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
    
    async def login(self) -> bool:
        max_attempts = RETRY_CONFIG["max_attempts"]
        
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
                    log_warning("Captcha çözülemedi, sayfa yenileniyor...")
                    await asyncio.sleep(1)
                    continue
                
                # Giriş butonuna tıkla
                await self.page.click('button.btn-login')
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                # Giriş başarılı mı kontrol et
                if await self._check_login_success():
                    log_success("Giriş başarılı!")
                    return True
                else:
                    log_warning("Giriş başarısız - captcha yanlış olabilir")
                    
            except Exception as e:
                log_error(f"Giriş hatası: {e}")
            
            await asyncio.sleep(RETRY_CONFIG["delay_between_attempts"])
        
        log_error(f"Giriş {max_attempts} denemeden sonra başarısız!")
        return False
    
    async def _solve_captcha(self) -> bool:
        """Selçuk ÖBS captcha çözücü"""
        try:
            # Captcha görseli: img#Image1
            captcha_element = await self.page.query_selector('img#Image1')
            
            if not captcha_element:
                log_warning("Captcha görseli bulunamadı")
                return False
            
            # Görselin ekran görüntüsünü al
            screenshot_bytes = await captcha_element.screenshot()
            log_debug("Captcha görseli yakalandı")
            
            # OCR ile çöz (4 haneli sayı bekleniyor)
            captcha_text = self.ocr_handler.extract_with_retry(screenshot_bytes, expected_length=4)
            
            if not captcha_text:
                log_warning("OCR boş sonuç döndürdü")
                return False
            
            log_info(f"Captcha çözüldü: {captcha_text}")
            
            # Captcha input alanı: input#TxtCaptcha
            await self.page.fill('input#TxtCaptcha', captcha_text)
            log_debug("Captcha kodu girildi")
            
            return True
            
        except Exception as e:
            log_error(f"Captcha çözme hatası: {e}")
            return False
    
    async def _check_login_success(self) -> bool:
        """Giriş başarılı mı kontrol et"""
        try:
            current_url = self.page.url.lower()
            
            # Hala ana sayfadaysak başarısız
            if current_url.endswith('/') or 'login' in current_url:
                # Hata mesajı var mı kontrol et
                error_el = await self.page.query_selector('.alert-danger, .error, .hata')
                if error_el:
                    error_text = await error_el.inner_text()
                    log_warning(f"Hata mesajı: {error_text}")
                return False
            
            # Başarılı giriş göstergeleri
            if 'anasayfa' in current_url or 'home' in current_url or 'ogrenci' in current_url:
                return True
            
            # URL değiştiyse muhtemelen başarılı
            return current_url != self.login_url.lower()
            
        except Exception as e:
            log_error(f"Giriş kontrolü hatası: {e}")
            return False
    
    async def fetch_grades(self) -> Dict:
        """Notları çek - Selçuk ÖBS yapısına uygun"""
        grades = {}
        
        try:
            # Not sayfasına git
            log_info("Not sayfasına gidiliyor...")
            await self.page.goto(self.grades_url, wait_until="networkidle")
            await asyncio.sleep(3)
            
            # Alternatif URL'ler dene
            if "NotListesi" not in self.page.url:
                # Menüden not sayfasına gitmeyi dene
                alt_urls = [
                    f"{OBS_URL}/OgrenciIsleri/NotListesi",
                    f"{OBS_URL}/Ogrenci/NotListesi",
                    f"{OBS_URL}/not-listesi",
                ]
                for url in alt_urls:
                    try:
                        await self.page.goto(url, wait_until="networkidle")
                        await asyncio.sleep(2)
                        if "not" in self.page.url.lower():
                            break
                    except:
                        continue
            
            log_debug(f"Sayfa URL: {self.page.url}")
            
            # Tablo satırlarını bul
            # Farklı tablo yapılarını dene
            table_selectors = [
                'table.table tbody tr',
                'table.dataTable tbody tr',
                '.not-tablosu tr',
                'table tr',
                '#notListesi tr'
            ]
            
            rows = []
            for selector in table_selectors:
                rows = await self.page.query_selector_all(selector)
                if len(rows) > 1:
                    log_debug(f"Tablo bulundu: {selector} ({len(rows)} satır)")
                    break
            
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 2:
                    try:
                        texts = []
                        for cell in cells:
                            text = await cell.inner_text()
                            texts.append(text.strip())
                        
                        # Boş satırları atla
                        if not any(texts):
                            continue
                        
                        # Tipik yapı: Ders Kodu | Ders Adı | Kredi | Vize | Final | Ortalama
                        course_name = texts[1] if len(texts) > 1 and texts[1] else texts[0]
                        
                        if course_name and len(course_name) > 2:
                            grades[course_name] = {
                                "kod": texts[0] if len(texts) > 0 else "",
                                "vize": texts[3] if len(texts) > 3 else "",
                                "final": texts[4] if len(texts) > 4 else "",
                                "not": texts[-1] if texts[-1] else ""
                            }
                            log_debug(f"Ders: {course_name}")
                            
                    except Exception as e:
                        log_debug(f"Satır işlenemedi: {e}")
                        continue
            
            log_success(f"Toplam {len(grades)} ders notu çekildi")
            
        except Exception as e:
            log_error(f"Not çekme hatası: {e}")
        
        return grades
    
    async def run(self) -> Tuple[bool, Dict]:
        try:
            await self.start()
            if await self.login():
                grades = await self.fetch_grades()
                return (True, grades)
            return (False, {})
        except Exception as e:
            log_error(f"Bot hatası: {e}")
            return (False, {})
        finally:
            await self.stop()


async def run_bot() -> Tuple[bool, Dict]:
    bot = OBSBot()
    return await bot.run()
