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

            # 6. Son çare - Gelişmiş OCR (7 farklı strateji ile)
            if not captcha_text and captcha_element:
                log_info("HTML'de captcha bulunamadı, Gelişmiş OCR sistemi devreye giriyor...")
                
                # Captcha görselini yüksek kalitede al
                screenshot_bytes = await captcha_element.screenshot(type="png")
                
                # Orijinal görseli debug için kaydet
                try:
                    with open("temp/captcha_original.png", "wb") as f:
                        f.write(screenshot_bytes)
                    log_debug("Orijinal captcha görseli kaydedildi: temp/captcha_original.png")
                except:
                    pass
                
                # Gelişmiş OCR ile çöz (7 farklı strateji deneyecek)
                captcha_text = self.ocr_handler.extract_with_retry(screenshot_bytes, expected_length=4)
                
                if captcha_text:
                    log_success(f"✓ Captcha OCR ile çözüldü: {captcha_text}")
                else:
                    log_warning("OCR tüm stratejileri denedi ama sonuç bulunamadı")

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
                msg = "Giriş başarısız oldu"
                
                # 1. Kırmızı span hata mesajı (Genellikle burada yazar)
                # <span style="color:red;font-family:Arial, Helvetica, sans-serif;">Hatalı şifre</span>
                span_error = await self.page.query_selector('span[style*="color:red"]')
                if span_error:
                    text = (await span_error.inner_text()).strip()
                    if text:
                        msg = f"Hata: {text}"
                        log_warning(msg)
                        return False, msg

                # 2. Alert kutusu (ama 'hide' class'ı olmayacak ve şablon metni olmayacak)
                alert_el = await self.page.query_selector('.alert-danger:not(.hide)')
                if alert_el:
                    text = (await alert_el.inner_text()).strip()
                    # Şablon mesajını filtrele
                    if text and "Your Error Message goes here" not in text:
                        msg = f"Hata: {text.replace('Error!', '').strip()}"
                        log_warning(msg)
                        return False, msg
                
                # 3. Genel hata kontrolü
                return False, "Giriş yapılamadı (Captcha veya Şifre hatası)"
            
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

    async def _check_still_logged_in(self) -> bool:
        """Hala oturum açık mı kontrol et"""
        try:
            page_content = await self.page.content()
            page_content_lower = page_content.lower()
            
            # Login sayfasına geri dönmüşsek oturum kapanmış demektir
            if 'txtcaptcha' in page_content_lower or 'btn-login' in page_content_lower:
                return False
            
            return True
        except:
            return False

    async def fetch_grades(self) -> Dict:
        """
        Son Yıl Notları sayfasına git ve notları çek.
        
        Returns:
            Notlar sözlüğü: {"ders_kodu": {"ders_adi": str, "vize1": str, ...}, ...}
        """
        try:
            log_info("SonYilNotlari sayfasına gidiliyor...")
            
            # Önce menüden link'e tıklayarak gitmeyi dene (daha güvenilir session yönetimi)
            navigated = await self._navigate_to_grades_via_menu()
            
            if not navigated:
                # Menüden gidilemezse doğrudan URL'ye git
                log_info("Menüden gidilemedi, doğrudan URL deneniyor...")
                await self.page.goto(self.grades_url, wait_until="networkidle")
                await asyncio.sleep(2)
            
            # Oturum hala açık mı kontrol et
            if not await self._check_still_logged_in():
                log_error("Oturum kapatılmış! Login sayfasına geri dönüldü.")
                # Tekrar giriş yapmayı dene
                log_info("Tekrar giriş deneniyor...")
                is_login, login_error = await self.login()
                if not is_login:
                    log_error(f"Tekrar giriş başarısız: {login_error}")
                    return {}
                
                # Başarılı giriş sonrası menüden gitmeyi tekrar dene
                log_info("Giriş başarılı, SonYilNotlari sayfasına menüden gidiliyor...")
                navigated = await self._navigate_to_grades_via_menu()
                
                if not navigated:
                    # Son çare - doğrudan URL
                    await self.page.goto(self.grades_url, wait_until="networkidle")
                    await asyncio.sleep(2)
                
                # Tekrar kontrol et
                if not await self._check_still_logged_in():
                    log_error("Notlar sayfasına erişilemiyor, oturum sorunu devam ediyor.")
                    return {}
            
            log_success("SonYilNotlari sayfası yüklendi")
            
            # Notları parse et
            grades = await self._parse_grades()
            
            return grades
            
        except Exception as e:
            log_error(f"Notları çekme hatası: {e}")
            return {}

    async def _navigate_to_grades_via_menu(self) -> bool:
        """
        Menü üzerinden SonYilNotlari sayfasına git.
        Bu yöntem session cookie'lerini korur.
        """
        try:
            # Olası menü linkleri
            link_selectors = [
                'a[href*="SonYilNotlari"]',
                'a[href*="sonyilnotlari"]',
                'a[href*="Sonyilnotlari"]',
                'a:has-text("Son Yıl Notları")',
                'a:has-text("Son yıl notları")',
                'a:has-text("Notlar")',
                'a:has-text("Not Durumu")',
                # Menü altındaki linkler
                '.nav a[href*="Notlari"]',
                '.menu a[href*="Notlari"]',
                '#menu a[href*="Notlari"]',
                'li a[href*="Notlari"]'
            ]
            
            for selector in link_selectors:
                try:
                    link = await self.page.query_selector(selector)
                    if link:
                        log_debug(f"SonYilNotlari linki bulundu: {selector}")
                        await link.click()
                        await self.page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        log_success("Menüden SonYilNotlari sayfasına gidildi")
                        return True
                except Exception as e:
                    log_debug(f"Link seçici {selector} denemesi başarısız: {e}")
                    continue
            
            log_debug("Menüde SonYilNotlari linki bulunamadı")
            return False
            
        except Exception as e:
            log_error(f"Menüden navigasyon hatası: {e}")
            return False

    async def _parse_grades(self) -> Dict:
        """
        Sayfadaki not tablosunu parse et.
        
        Returns:
            Notlar sözlüğü
        """
        grades = {}
        
        try:
            # Sayfanın tam yüklenmesini bekle
            await asyncio.sleep(1)
            
            # Not tablosunu bul - farklı tablo yapılarını dene
            table_selectors = [
                'table.table',
                'table.gridview',
                'table#GridView1',
                'table.table-bordered',
                '#ctl00_ContentPlaceHolder1_GridView1',
                'table'
            ]
            
            table = None
            for selector in table_selectors:
                table = await self.page.query_selector(selector)
                if table:
                    log_debug(f"Not tablosu bulundu: {selector}")
                    break
            
            if not table:
                log_warning("Not tablosu bulunamadı!")
                # Sayfa içeriğini debug için kaydet
                page_content = await self.page.content()
                log_debug(f"Sayfa içeriği (ilk 500 karakter): {page_content[:500]}")
                return grades
            
            # Tablo satırlarını al
            rows = await table.query_selector_all('tr')
            log_debug(f"Toplam {len(rows)} satır bulundu")
            
            # Dönem ortalamasını sayfadan almaya çalış
            donem_ortalamasi = await self._get_donem_ortalamasi()
            if donem_ortalamasi:
                grades["_donem_ortalamasi"] = donem_ortalamasi
            
            # Her satırı işle (ilk satır başlık olabilir)
            for i, row in enumerate(rows):
                try:
                    cells = await row.query_selector_all('td')
                    
                    # En az birkaç hücre olmalı
                    if len(cells) < 3:
                        continue
                    
                    # Hücre değerlerini al
                    cell_values = []
                    for cell in cells:
                        text = (await cell.inner_text()).strip()
                        cell_values.append(text)
                    
                    # Boş satırları atla
                    if not any(cell_values):
                        continue
                    
                    # Ders kodunu ve bilgilerini parse et
                    # Tipik yapı: [Ders Kodu, Ders Adı, Kredi, Vize1, Vize2, Final, Büt, GN, Harf, Durum]
                    # Ancak yapı değişebilir, bu yüzden esnek olmalıyız
                    
                    grade_info = self._parse_row_to_grade(cell_values)
                    
                    if grade_info and grade_info.get("ders_kodu"):
                        ders_kodu = grade_info["ders_kodu"]
                        grades[ders_kodu] = grade_info
                        log_debug(f"Ders bulundu: {ders_kodu} - {grade_info.get('ders_adi', 'N/A')}")
                        
                except Exception as e:
                    log_debug(f"Satır {i} parse hatası: {e}")
                    continue
            
            log_info(f"Toplam {len([k for k in grades if not k.startswith('_')])} ders bulundu")
            
        except Exception as e:
            log_error(f"Not parse hatası: {e}")
        
        return grades

    def _parse_row_to_grade(self, cells: list) -> Optional[Dict]:
        """
        Satır hücrelerini not bilgisine dönüştür.
        Farklı tablo formatlarını destekler.
        """
        if len(cells) < 3:
            return None
        
        # Ders kodu genellikle ilk hücrede
        ders_kodu = cells[0] if cells[0] else None
        
        # Ders kodu boşsa veya "Ders Kodu" gibi başlık ise atla
        if not ders_kodu or ders_kodu.lower() in ['ders kodu', 'kod', 'code', 'no', 'sıra']:
            return None
        
        grade_info = {
            "ders_kodu": ders_kodu,
            "ders_adi": cells[1] if len(cells) > 1 else "",
            "kredi": cells[2] if len(cells) > 2 else "",
            "vize1": "",
            "vize2": "",
            "vize3": "",
            "vize4": "",
            "final": "",
            "but": "",
            "gn": "",
            "harf": "",
            "durum": ""
        }
        
        # Hücre sayısına göre alanları doldur
        # Selçuk ÖBS tipik yapısı: Kod, Ad, T, U, K, AKTS, Vize1, Vize2, Final, Büt, YS, BN, BD, Durum
        # veya daha basit: Kod, Ad, Kredi, Vize, Final, Büt, Harf
        
        if len(cells) >= 14:
            # Detaylı tablo yapısı
            grade_info["vize1"] = cells[6] if len(cells) > 6 else ""
            grade_info["vize2"] = cells[7] if len(cells) > 7 else ""
            grade_info["final"] = cells[8] if len(cells) > 8 else ""
            grade_info["but"] = cells[9] if len(cells) > 9 else ""
            grade_info["gn"] = cells[11] if len(cells) > 11 else ""  # Başarı Notu
            grade_info["harf"] = cells[12] if len(cells) > 12 else ""  # Başarı Derecesi
            grade_info["durum"] = cells[13] if len(cells) > 13 else ""
        elif len(cells) >= 10:
            # Orta detay tablo yapısı
            grade_info["vize1"] = cells[3] if len(cells) > 3 else ""
            grade_info["vize2"] = cells[4] if len(cells) > 4 else ""
            grade_info["final"] = cells[5] if len(cells) > 5 else ""
            grade_info["but"] = cells[6] if len(cells) > 6 else ""
            grade_info["gn"] = cells[7] if len(cells) > 7 else ""
            grade_info["harf"] = cells[8] if len(cells) > 8 else ""
            grade_info["durum"] = cells[9] if len(cells) > 9 else ""
        elif len(cells) >= 7:
            # Basit tablo yapısı
            grade_info["vize1"] = cells[3] if len(cells) > 3 else ""
            grade_info["final"] = cells[4] if len(cells) > 4 else ""
            grade_info["but"] = cells[5] if len(cells) > 5 else ""
            grade_info["harf"] = cells[6] if len(cells) > 6 else ""
        elif len(cells) >= 4:
            # Minimal tablo yapısı
            grade_info["vize1"] = cells[2] if len(cells) > 2 else ""
            grade_info["final"] = cells[3] if len(cells) > 3 else ""
        
        return grade_info

    async def _get_donem_ortalamasi(self) -> str:
        """Dönem ortalamasını sayfadan al"""
        try:
            # Dönem ortalaması genellikle bir label veya span'da olur
            selectors = [
                '#ctl00_ContentPlaceHolder1_lblOrtalama',
                '.ortalama',
                'span:has-text("Ortalama")',
                'td:has-text("Dönem Ort")'
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        text = (await element.inner_text()).strip()
                        # Sayısal değeri çıkar
                        import re
                        match = re.search(r'(\d+[.,]\d+)', text)
                        if match:
                            return match.group(1)
                except:
                    continue
            
            return ""
        except:
            return ""

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
