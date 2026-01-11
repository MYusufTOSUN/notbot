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
                    log_warning(f"Site hatası: {indicator}")
                    return False
            
            # Hala login sayfasındaysa başarısız
            if 'txtcaptcha' in page_content_lower or 'btn-login' in page_content_lower:
                error_el = await self.page.query_selector('.alert-danger, .alert-warning')
                if error_el:
                    error_text = await error_el.inner_text()
                    log_warning(f"Hata: {error_text}")
                return False
            
            # Başarılı giriş göstergeleri
            success_indicators = ['anasayfa', 'çıkış', 'cikis', 'logout', 'son yıl notları', 'not durumu']
            for indicator in success_indicators:
                if indicator in page_content_lower:
                    log_debug(f"Giriş başarılı - gösterge: {indicator}")
                    return True
            
            log_warning("Giriş göstergesi bulunamadı")
            return False
            
        except Exception as e:
            log_error(f"Giriş kontrolü hatası: {e}")
            return False
    
    async def fetch_grades(self) -> Dict:
        """Notları çek - Selçuk ÖBS SonYilNotlari sayfasına uygun"""
        grades = {}
        
        try:
            log_info("Not sayfasına gidiliyor...")
            await self.page.goto(self.grades_url, wait_until="networkidle")
            await asyncio.sleep(2)
            
            log_debug(f"Sayfa URL: {self.page.url}")
            
            # Tablo satırlarını bul - #dynamic-table tbody tr
            rows = await self.page.query_selector_all('#dynamic-table tbody tr')
            
            if not rows:
                # Alternatif selector dene
                rows = await self.page.query_selector_all('table.table-striped tbody tr')
            
            log_debug(f"Bulunan satır sayısı: {len(rows)}")
            
            for row in rows:
                cells = await row.query_selector_all('td')
                if len(cells) >= 13:  # En az 13 sütun olmalı
                    try:
                        # Sütun yapısı:
                        # 0:Ders Kodu, 1:Yarı Yıl, 2:Ders Adı, 3:Kredi, 
                        # 4:Vize1, 5:Vize2, 6:Vize3, 7:Vize4, 
                        # 8:Final, 9:Büt, 10:Muaf-2, 11:GN, 12:Harf, 13:Durum
                        
                        ders_kodu = (await cells[0].inner_text()).strip()
                        ders_adi = (await cells[2].inner_text()).strip()
                        kredi = (await cells[3].inner_text()).strip()
                        vize1 = (await cells[4].inner_text()).strip()
                        final = (await cells[8].inner_text()).strip()
                        but = (await cells[9].inner_text()).strip()
                        gn = (await cells[11].inner_text()).strip()
                        harf = (await cells[12].inner_text()).strip().replace('--', '')
                        
                        # Durum kontrolü
                        durum = ""
                        if len(cells) > 13:
                            durum = (await cells[13].inner_text()).strip()
                        
                        if ders_adi:
                            grades[ders_kodu] = {
                                "ders_adi": ders_adi,
                                "kredi": kredi,
                                "vize1": vize1,
                                "final": final,
                                "but": but,
                                "gn": gn,
                                "harf": harf,
                                "durum": durum
                            }
                            log_debug(f"Ders: {ders_adi} | Vize:{vize1} | Final:{final} | Harf:{harf}")
                            
                    except Exception as e:
                        log_debug(f"Satır işlenemedi: {e}")
                        continue
            
            # Dönem ortalamasını çek (ikinci tablo)
            try:
                ortalama_tables = await self.page.query_selector_all('table.table-striped.table-bordered.container tbody')
                if ortalama_tables:
                    ortalama_rows = await ortalama_tables[0].query_selector_all('tr')
                    donem_ortalamasi = ""
                    for orow in ortalama_rows:
                        ocells = await orow.query_selector_all('td')
                        if len(ocells) >= 2:
                            label = (await ocells[0].inner_text()).strip().lower()
                            value = (await ocells[1].inner_text()).strip()
                            if 'dönem' in label and 'ortalama' in label:
                                donem_ortalamasi = value
                                log_debug(f"Dönem ortalaması: {value}")
                    
                    if donem_ortalamasi:
                        grades["_donem_ortalamasi"] = donem_ortalamasi
            except Exception as e:
                log_debug(f"Ortalama çekilemedi: {e}")
            
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
