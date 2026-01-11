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
        """Notları çek - Selçuk ÖBS Son Yıl Notları sayfasına uygun"""
        grades = {}
        
        try:
            # Not sayfasına git
            log_info("Not sayfasına gidiliyor...")
            await self.page.goto(self.grades_url, wait_until="networkidle")
            await asyncio.sleep(3)
            
            log_debug(f"Sayfa URL: {self.page.url}")
            
            # Tablo satırlarını bul - #dynamic-table veya table.table-striped
            table_selectors = [
                '#dynamic-table tbody tr',
                'table.table-striped tbody tr',
                'table.table-bordered tbody tr',
                'table.table tbody tr',
            ]
            
            rows = []
            for selector in table_selectors:
                rows = await self.page.query_selector_all(selector)
                if len(rows) > 0:
                    log_debug(f"Tablo bulundu: {selector} ({len(rows)} satır)")
                    break
            
            # Selçuk ÖBS Son Yıl Notları tablo yapısı:
            # 0: Ders Kodu | 1: Yarı Yıl | 2: Ders Adı | 3: Kredi(AKTS)
            # 4: Vize1 | 5: Vize2 | 6: Vize3 | 7: Vize4
            # 8: Final | 9: Büt | 10: Muaf-2 | 11: GN (Genel Not)
            # 12: Harf | 13: Durum | 14: (Harf Düzeyleri link)
            
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 10:  # En az temel sütunlar olmalı
                    try:
                        texts = []
                        for cell in cells:
                            text = await cell.inner_text()
                            texts.append(text.strip())
                        
                        # Boş satırları atla
                        if not any(texts):
                            continue
                        
                        ders_kodu = texts[0] if len(texts) > 0 else ""
                        ders_adi = texts[2] if len(texts) > 2 else ""
                        
                        # Ders adı yoksa veya çok kısaysa atla
                        if not ders_adi or len(ders_adi) < 3:
                            continue
                        
                        # Not bilgilerini çıkar
                        grade_data = {
                            "kod": ders_kodu,
                            "yariyil": texts[1] if len(texts) > 1 else "",
                            "kredi": texts[3] if len(texts) > 3 else "",
                            "vize1": texts[4] if len(texts) > 4 else "",
                            "vize2": texts[5] if len(texts) > 5 else "",
                            "vize3": texts[6] if len(texts) > 6 else "",
                            "vize4": texts[7] if len(texts) > 7 else "",
                            "final": texts[8] if len(texts) > 8 else "",
                            "but": texts[9] if len(texts) > 9 else "",
                            "muaf2": texts[10] if len(texts) > 10 else "",
                            "gn": texts[11] if len(texts) > 11 else "",
                            "harf": texts[12].replace("--", "").strip() if len(texts) > 12 else "",
                            "durum": texts[13] if len(texts) > 13 else ""
                        }
                        
                        grades[ders_adi] = grade_data
                        log_debug(f"Ders: {ders_adi} | Vize1: {grade_data['vize1']} | Final: {grade_data['final']} | Harf: {grade_data['harf']}")
                            
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
