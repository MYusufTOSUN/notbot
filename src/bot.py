"""
Ana Bot Modülü - Selçuk Üniversitesi ÖBS (OBİS) için özelleştirilmiş
Playwright ile giriş yapar, captcha çözer ve notları çeker.

SIFIRDAN YAZILDI - Session yönetimi düzeltildi
"""
import asyncio
import re
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
        self.base_url = OBS_URL.rstrip('/')
        
    async def start(self):
        """Tarayıcıyı başlat"""
        log_info("Tarayıcı başlatılıyor...")
        self._playwright = await async_playwright().start()
        
        self.browser = await self._playwright.chromium.launch(
            headless=BROWSER_CONFIG["headless"],
            slow_mo=BROWSER_CONFIG["slow_mo"]
        )
        
        # Context oluştururken cookie'leri kabul et
        self.context = await self.browser.new_context(
            viewport=BROWSER_CONFIG["viewport"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True,
            java_script_enabled=True,
            ignore_https_errors=True
        )
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(BROWSER_CONFIG["timeout"])
        log_success("Tarayıcı başlatıldı")
    
    async def stop(self):
        """Tarayıcıyı kapat"""
        try:
            if self.page: 
                await self.page.close()
            if self.context: 
                await self.context.close()
            if self.browser: 
                await self.browser.close()
            if self._playwright: 
                await self._playwright.stop()
            self.ocr_handler.cleanup()
            log_info("Tarayıcı kapatıldı")
        except Exception as e:
            log_error(f"Tarayıcı kapatma hatası: {e}")

    async def login(self) -> Tuple[bool, str]:
        """ÖBS'ye giriş yap"""
        max_attempts = RETRY_CONFIG["max_attempts"]
        last_error = ""
        
        for attempt in range(1, max_attempts + 1):
            try:
                log_info(f"Giriş denemesi {attempt}/{max_attempts}")
                
                # Login sayfasına git
                await self.page.goto(self.base_url, wait_until="networkidle")
                await asyncio.sleep(1)
                
                current_url = self.page.url
                log_debug(f"Mevcut URL: {current_url}")
                
                # Form alanlarını doldur
                await self.page.fill('input[name="id"]', OBS_USERNAME)
                log_debug("Öğrenci numarası girildi")
                
                await self.page.fill('input[name="pass"]', OBS_PASSWORD)
                log_debug("Şifre girildi")
                
                # Captcha çöz
                captcha_solved = await self._solve_captcha()
                if not captcha_solved:
                    last_error = "Captcha çözülemedi"
                    log_warning(f"{last_error}, tekrar deneniyor...")
                    await asyncio.sleep(1)
                    continue
                
                # Giriş butonuna tıkla
                await self.page.click('button.btn-login')
                
                # Sayfa yüklenmesini bekle
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)
                
                # Giriş sonrası URL'yi kontrol et
                new_url = self.page.url
                log_debug(f"Giriş sonrası URL: {new_url}")
                
                # Giriş başarılı mı kontrol et
                success, error_msg = await self._check_login_success()
                
                if success:
                    log_success("Giriş başarılı!")
                    log_debug(f"Giriş sonrası sayfa: {new_url}")
                    return True, ""
                else:
                    last_error = error_msg or "Giriş başarısız"
                    log_warning(f"{last_error}")
                    
            except Exception as e:
                last_error = str(e)
                log_error(f"Giriş hatası: {e}")
            
            await asyncio.sleep(RETRY_CONFIG["delay_between_attempts"])
        
        log_error(f"Giriş {max_attempts} denemeden sonra başarısız!")
        return False, last_error

    async def _solve_captcha(self) -> bool:
        """Captcha'yı çöz"""
        try:
            captcha_text = None
            
            # Captcha görseli
            captcha_element = await self.page.query_selector('img#Image1')
            
            if not captcha_element:
                log_warning("Captcha görseli bulunamadı!")
                return False
            
            # 1. Title veya alt attribute'dan al
            title_text = await captcha_element.get_attribute('title')
            alt_text = await captcha_element.get_attribute('alt')
            
            if title_text and title_text.isdigit() and len(title_text) == 4:
                captcha_text = title_text
                log_info(f"Captcha title'dan alındı: {captcha_text}")
            elif alt_text and alt_text.isdigit() and len(alt_text) == 4:
                captcha_text = alt_text
                log_info(f"Captcha alt'tan alındı: {captcha_text}")
            
            # 2. Parent element kontrolü
            if not captcha_text:
                try:
                    parent = await captcha_element.query_selector('xpath=..')
                    if parent:
                        parent_title = await parent.get_attribute('title')
                        if parent_title and parent_title.isdigit() and len(parent_title) == 4:
                            captcha_text = parent_title
                            log_info(f"Captcha parent title'dan alındı: {captcha_text}")
                except:
                    pass
            
            # 3. Hidden input kontrolü
            if not captcha_text:
                hidden_inputs = await self.page.query_selector_all('input[type="hidden"]')
                for inp in hidden_inputs:
                    value = await inp.get_attribute('value')
                    if value and value.isdigit() and len(value) == 4:
                        captcha_text = value
                        log_info(f"Captcha hidden input'tan alındı: {captcha_text}")
                        break
            
            # 4. Sayfa kaynağında ara
            if not captcha_text:
                page_content = await self.page.content()
                # Tooltip pattern
                matches = re.findall(r'["\'](\d{4})["\']', page_content)
                for match in matches:
                    if match.isdigit() and len(match) == 4:
                        captcha_text = match
                        log_info(f"Captcha sayfa kaynağından alındı: {captcha_text}")
                        break
            
            # 5. OCR ile çöz
            if not captcha_text:
                log_info("OCR ile captcha çözülüyor...")
                screenshot_bytes = await captcha_element.screenshot(type="png")
                
                # Debug için kaydet
                try:
                    with open("temp/captcha_original.png", "wb") as f:
                        f.write(screenshot_bytes)
                except:
                    pass
                
                captcha_text = self.ocr_handler.extract_with_retry(screenshot_bytes, expected_length=4)
                
                if captcha_text:
                    log_success(f"Captcha OCR ile çözüldü: {captcha_text}")
            
            if not captcha_text:
                log_warning("Captcha çözülemedi!")
                return False
            
            # Captcha'yı gir
            await self.page.fill('input#TxtCaptcha', captcha_text)
            log_debug(f"Captcha girildi: {captcha_text}")
            
            return True
            
        except Exception as e:
            log_error(f"Captcha çözme hatası: {e}")
            return False

    async def _check_login_success(self) -> Tuple[bool, str]:
        """Giriş başarılı mı kontrol et"""
        try:
            page_content = await self.page.content()
            page_lower = page_content.lower()
            current_url = self.page.url.lower()
            
            # Hata mesajları
            if 'hatalı' in page_lower or 'yanlış' in page_lower:
                span_error = await self.page.query_selector('span[style*="color:red"]')
                if span_error:
                    text = (await span_error.inner_text()).strip()
                    if text:
                        return False, f"Hata: {text}"
                return False, "Kullanıcı adı veya şifre hatalı"
            
            # Hala login sayfasındaysa
            if 'txtcaptcha' in page_lower and 'btn-login' in page_lower:
                return False, "Giriş yapılamadı (Captcha yanlış olabilir)"
            
            # Başarılı giriş göstergeleri
            success_indicators = [
                'ogrenci',  # URL'de ogrenci varsa
                'anasayfa',
                'hoşgeldiniz',
                'hosgeldiniz', 
                'çıkış',
                'cikis',
                'logout',
                'öğrenci bilgi',
                'ogrenci bilgi'
            ]
            
            for indicator in success_indicators:
                if indicator in page_lower or indicator in current_url:
                    return True, ""
            
            # URL değişmişse muhtemelen giriş başarılı
            if 'ogrenci' in current_url or '/Ogrenci' in self.page.url:
                return True, ""
            
            return False, "Giriş göstergesi bulunamadı"
            
        except Exception as e:
            return False, f"Kontrol hatası: {e}"

    async def fetch_grades(self) -> Dict:
        """
        Notları çek - Ana metod
        """
        try:
            log_info("=" * 50)
            log_info("NOTLARI ÇEKME İŞLEMİ BAŞLIYOR")
            log_info("=" * 50)
            
            # Mevcut URL'yi logla
            current_url = self.page.url
            log_info(f"Mevcut sayfa: {current_url}")
            
            # Sayfadaki tüm linkleri bul ve logla
            await self._log_available_links()
            
            # SonYilNotlari sayfasına git
            success = await self._go_to_grades_page()
            
            if not success:
                log_error("SonYilNotlari sayfasına gidilemedi!")
                return {}
            
            # Notları parse et
            grades = await self._parse_grades_table()
            
            return grades
            
        except Exception as e:
            log_error(f"Notları çekme hatası: {e}")
            import traceback
            log_error(traceback.format_exc())
            return {}

    async def _log_available_links(self):
        """Sayfadaki tüm linkleri logla (debug için)"""
        try:
            links = await self.page.query_selector_all('a')
            log_debug(f"Sayfada {len(links)} link bulundu:")
            
            for link in links[:20]:  # İlk 20 link
                href = await link.get_attribute('href')
                text = (await link.inner_text()).strip()[:50]
                if href and ('not' in href.lower() or 'not' in text.lower()):
                    log_info(f"  📎 [{text}] -> {href}")
                    
        except Exception as e:
            log_debug(f"Link loglama hatası: {e}")

    async def _go_to_grades_page(self) -> bool:
        """SonYilNotlari sayfasına git"""
        try:
            # Yöntem 1: Sayfadaki linke tıkla
            link_patterns = [
                'a[href*="SonYilNotlari"]',
                'a[href*="Sonyilnotlari"]', 
                'a[href*="sonyilnotlari"]',
                'a[href*="SONYILNOTLARI"]',
            ]
            
            for pattern in link_patterns:
                try:
                    link = await self.page.query_selector(pattern)
                    if link:
                        log_info(f"Link bulundu: {pattern}")
                        await link.click()
                        await self.page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        
                        # Login sayfasına dönmüş mü kontrol et
                        if not await self._is_on_login_page():
                            log_success("SonYilNotlari sayfasına gidildi (link ile)")
                            return True
                        else:
                            log_warning("Link tıklandı ama login sayfasına döndü")
                except Exception as e:
                    log_debug(f"Link tıklama hatası ({pattern}): {e}")
                    continue
            
            # Yöntem 2: Metin içeren linke tıkla
            text_patterns = [
                "Son Yıl Notları",
                "Son yıl notları", 
                "SON YIL NOTLARI",
                "Notlarım",
                "NOTLARIM"
            ]
            
            for text in text_patterns:
                try:
                    link = await self.page.query_selector(f'a:has-text("{text}")')
                    if link:
                        log_info(f"Metin linki bulundu: {text}")
                        await link.click()
                        await self.page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        
                        if not await self._is_on_login_page():
                            log_success("SonYilNotlari sayfasına gidildi (metin ile)")
                            return True
                except Exception as e:
                    log_debug(f"Metin link hatası ({text}): {e}")
                    continue
            
            # Yöntem 3: JavaScript ile navigasyon
            try:
                log_info("JavaScript navigasyon deneniyor...")
                await self.page.evaluate('''() => {
                    const links = document.querySelectorAll('a');
                    for (let link of links) {
                        if (link.href && link.href.toLowerCase().includes('sonyilnotlari')) {
                            link.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                if not await self._is_on_login_page():
                    log_success("SonYilNotlari sayfasına gidildi (JS ile)")
                    return True
            except Exception as e:
                log_debug(f"JS navigasyon hatası: {e}")
            
            # Yöntem 4: Doğrudan URL'ye git (farklı varyasyonlar)
            url_variants = [
                f"{self.base_url}/Ogrenci/SonYilNotlari",
                f"{self.base_url}/Ogrenci/Sonyilnotlari",
                f"{self.base_url}/Ogrenci/sonyilnotlari",
                f"{self.base_url}/ogrenci/SonYilNotlari",
                f"{self.base_url}/ogrenci/sonyilnotlari",
            ]
            
            for url in url_variants:
                try:
                    log_info(f"URL deneniyor: {url}")
                    
                    # Mevcut cookie'leri koru
                    cookies = await self.context.cookies()
                    log_debug(f"Mevcut cookie sayısı: {len(cookies)}")
                    
                    await self.page.goto(url, wait_until="networkidle")
                    await asyncio.sleep(2)
                    
                    new_url = self.page.url
                    log_debug(f"Sonuç URL: {new_url}")
                    
                    if not await self._is_on_login_page():
                        log_success(f"SonYilNotlari sayfasına gidildi: {url}")
                        return True
                    else:
                        log_warning(f"URL {url} login sayfasına yönlendirdi")
                        
                except Exception as e:
                    log_debug(f"URL hatası ({url}): {e}")
                    continue
            
            # Yöntem 5: Frame içinde ara
            try:
                frames = self.page.frames
                log_debug(f"Sayfa {len(frames)} frame içeriyor")
                
                for frame in frames:
                    if frame != self.page.main_frame:
                        frame_url = frame.url
                        log_debug(f"Frame URL: {frame_url}")
                        
                        if 'sonyilnotlari' in frame_url.lower():
                            log_success("SonYilNotlari frame içinde bulundu")
                            # Frame içeriğini işle
                            return True
            except Exception as e:
                log_debug(f"Frame kontrolü hatası: {e}")
            
            log_error("Hiçbir yöntem ile SonYilNotlari sayfasına gidilemedi!")
            
            # Debug: Mevcut sayfa içeriğini kaydet
            try:
                content = await self.page.content()
                with open("temp/debug_page.html", "w", encoding="utf-8") as f:
                    f.write(content)
                log_debug("Sayfa içeriği temp/debug_page.html dosyasına kaydedildi")
            except:
                pass
            
            return False
            
        except Exception as e:
            log_error(f"Sayfa navigasyon hatası: {e}")
            return False

    async def _is_on_login_page(self) -> bool:
        """Login sayfasında mıyız kontrol et"""
        try:
            page_content = await self.page.content()
            page_lower = page_content.lower()
            
            # Login sayfası göstergeleri
            if 'txtcaptcha' in page_lower or 'btn-login' in page_lower:
                return True
            
            # Captcha input'u var mı
            captcha_input = await self.page.query_selector('input#TxtCaptcha')
            if captcha_input:
                return True
            
            return False
            
        except:
            return False

    async def _parse_grades_table(self) -> Dict:
        """Not tablosunu parse et"""
        grades = {}
        
        try:
            log_info("Not tablosu aranıyor...")
            
            # Tabloyu bul
            table_selectors = [
                '#ctl00_ContentPlaceHolder1_gvSonYilNotlari',
                '#gvSonYilNotlari',
                'table.table',
                'table.gridview', 
                'table.GridView',
                'table#GridView1',
                'table.table-bordered',
                'table.table-striped',
                '.content table',
                '#content table',
                'table'
            ]
            
            table = None
            for selector in table_selectors:
                table = await self.page.query_selector(selector)
                if table:
                    # Tablonun gerçekten not tablosu olduğunu doğrula
                    table_html = await table.inner_html()
                    if 'ders' in table_html.lower() or 'not' in table_html.lower() or 'vize' in table_html.lower():
                        log_success(f"Not tablosu bulundu: {selector}")
                        break
                    else:
                        table = None
            
            if not table:
                log_warning("Not tablosu bulunamadı!")
                
                # Debug: Sayfadaki tabloları listele
                all_tables = await self.page.query_selector_all('table')
                log_debug(f"Sayfada {len(all_tables)} tablo var")
                
                return grades
            
            # Satırları al
            rows = await table.query_selector_all('tr')
            log_info(f"Tabloda {len(rows)} satır bulundu")
            
            # Header satırını analiz et
            header_row = rows[0] if rows else None
            if header_row:
                headers = await header_row.query_selector_all('th, td')
                header_texts = []
                for h in headers:
                    text = (await h.inner_text()).strip()
                    header_texts.append(text)
                log_debug(f"Tablo başlıkları: {header_texts}")
            
            # Her satırı işle
            for i, row in enumerate(rows[1:], start=1):  # İlk satır header
                try:
                    cells = await row.query_selector_all('td')
                    
                    if len(cells) < 2:
                        continue
                    
                    # Hücre değerlerini al
                    values = []
                    for cell in cells:
                        text = (await cell.inner_text()).strip()
                        values.append(text)
                    
                    # Boş satır kontrolü
                    if not any(values):
                        continue
                    
                    # Not bilgisini oluştur
                    grade_info = self._extract_grade_from_row(values, header_texts if header_row else [])
                    
                    if grade_info and grade_info.get("ders_kodu"):
                        key = grade_info["ders_kodu"]
                        grades[key] = grade_info
                        log_debug(f"Ders: {key} - {grade_info.get('ders_adi', 'N/A')}")
                        
                except Exception as e:
                    log_debug(f"Satır {i} parse hatası: {e}")
                    continue
            
            # Dönem ortalamasını al
            ortalama = await self._get_semester_average()
            if ortalama:
                grades["_donem_ortalamasi"] = ortalama
            
            log_success(f"Toplam {len([k for k in grades if not k.startswith('_')])} ders bulundu")
            
        except Exception as e:
            log_error(f"Tablo parse hatası: {e}")
        
        return grades

    def _extract_grade_from_row(self, values: list, headers: list) -> Optional[Dict]:
        """Satır değerlerinden not bilgisi çıkar - Header'a göre dinamik eşleme"""
        if len(values) < 3:
            return None
        
        # Başlangıç değerleri
        grade_info = {
            "ders_kodu": "",
            "ders_adi": "",
            "yariyil": "",
            "kredi": "",
            "vize1": "",
            "vize2": "",
            "final": "",
            "but": "",
            "gn": "",
            "harf": "",
            "durum": ""
        }
        
        # Header varsa, header'a göre dinamik eşle
        if headers and len(headers) >= 3:
            for i, header in enumerate(headers):
                if i >= len(values):
                    break
                    
                h_lower = header.lower().strip()
                val = values[i].strip() if values[i] else ""
                
                # Ders kodu tespiti
                if 'ders kodu' in h_lower or h_lower == 'kod' or h_lower == 'derskodu':
                    grade_info["ders_kodu"] = val
                # Ders adı tespiti
                elif 'ders ad' in h_lower or h_lower == 'ders' or 'adı' in h_lower or h_lower == 'ad':
                    grade_info["ders_adi"] = val
                # Yarıyıl tespiti
                elif 'yarıyıl' in h_lower or 'yariyil' in h_lower or 'dönem' in h_lower or 'donem' in h_lower:
                    grade_info["yariyil"] = val
                # Kredi
                elif 'kredi' in h_lower or 'akts' in h_lower:
                    grade_info["kredi"] = val
                # Vize notları
                elif 'vize' in h_lower or 'ara sınav' in h_lower or 'arasinav' in h_lower:
                    if not grade_info["vize1"]:
                        grade_info["vize1"] = val
                    else:
                        grade_info["vize2"] = val
                # Final
                elif 'final' in h_lower or 'dönem sonu' in h_lower:
                    grade_info["final"] = val
                # Bütünleme
                elif 'büt' in h_lower or 'but' in h_lower or 'bütünleme' in h_lower:
                    grade_info["but"] = val
                # Genel not / Başarı notu
                elif h_lower in ['bn', 'gn', 'not'] or 'başarı notu' in h_lower or 'basari notu' in h_lower or 'genel not' in h_lower:
                    grade_info["gn"] = val
                # Harf notu / Başarı derecesi
                elif h_lower in ['bd', 'harf'] or 'harf' in h_lower or 'başarı derece' in h_lower or 'derece' in h_lower:
                    grade_info["harf"] = val
                # Durum
                elif 'durum' in h_lower or 'sonuç' in h_lower or 'sonuc' in h_lower:
                    grade_info["durum"] = val
        
        # Header yoksa veya ders kodu/adı bulunamadıysa pozisyona göre tahmin et
        # Selçuk ÖBS yapısı: Ders Kodu, Yarıyıl, Ders Adı, T, U, K, AKTS, Vize1, Vize2, Final, Büt, YS, BN, BD, Durum
        if not grade_info["ders_kodu"] or not grade_info["ders_adi"]:
            log_debug(f"Header eşlemesi başarısız, pozisyona göre tahmin ediliyor. Değerler: {values[:5]}")
            
            # Selçuk ÖBS sabit yapısı:
            # Sütun 0: Ders Kodu
            # Sütun 1: Yarıyıl
            # Sütun 2: Ders Adı
            grade_info["ders_kodu"] = values[0] if len(values) > 0 else ""
            grade_info["yariyil"] = values[1] if len(values) > 1 else ""
            grade_info["ders_adi"] = values[2] if len(values) > 2 else ""
            
            # Notlar - sütun sayısına göre
            if len(values) >= 15:
                # Detaylı yapı: Kod, Yarıyıl, Ad, T, U, K, AKTS, Vize1, Vize2, Final, Büt, YS, BN, BD, Durum
                grade_info["vize1"] = values[7] if len(values) > 7 else ""
                grade_info["vize2"] = values[8] if len(values) > 8 else ""
                grade_info["final"] = values[9] if len(values) > 9 else ""
                grade_info["but"] = values[10] if len(values) > 10 else ""
                grade_info["gn"] = values[12] if len(values) > 12 else ""
                grade_info["harf"] = values[13] if len(values) > 13 else ""
                grade_info["durum"] = values[14] if len(values) > 14 else ""
            elif len(values) >= 10:
                # Orta yapı
                grade_info["vize1"] = values[5] if len(values) > 5 else ""
                grade_info["final"] = values[6] if len(values) > 6 else ""
                grade_info["but"] = values[7] if len(values) > 7 else ""
                grade_info["gn"] = values[8] if len(values) > 8 else ""
                grade_info["harf"] = values[9] if len(values) > 9 else ""
            elif len(values) >= 7:
                # Basit yapı
                grade_info["vize1"] = values[4] if len(values) > 4 else ""
                grade_info["final"] = values[5] if len(values) > 5 else ""
                grade_info["harf"] = values[6] if len(values) > 6 else ""
        
        # Ders kodu kontrolü - başlık satırı veya boş satır ise None döndür
        ders_kodu = grade_info["ders_kodu"]
        if not ders_kodu or ders_kodu.lower() in ['ders kodu', 'kod', 'code', 'no', 'sıra', '', 'yarıyıl', 'yariyil']:
            return None
        
        log_debug(f"Parse edildi: {grade_info['ders_kodu']} - {grade_info['ders_adi']}")
        
        return grade_info

    async def _get_semester_average(self) -> str:
        """Dönem ortalamasını al"""
        try:
            selectors = [
                '#ctl00_ContentPlaceHolder1_lblOrtalama',
                '#lblOrtalama',
                '.ortalama',
                'span:has-text("Ortalama")',
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        text = (await element.inner_text()).strip()
                        match = re.search(r'(\d+[.,]\d+)', text)
                        if match:
                            return match.group(1)
                except:
                    continue
            
            return ""
        except:
            return ""

    async def run(self) -> Tuple[bool, Dict, str]:
        """Ana çalıştırma metodu"""
        try:
            await self.start()
            
            # Giriş yap
            is_login, login_error = await self.login()
            
            if not is_login:
                return (False, {}, login_error)
            
            # Notları çek
            grades = await self.fetch_grades()
            
            return (True, grades, "")
            
        except Exception as e:
            log_error(f"Bot hatası: {e}")
            import traceback
            log_error(traceback.format_exc())
            return (False, {}, str(e))
            
        finally:
            await self.stop()


async def run_bot() -> Tuple[bool, Dict, str]:
    """Bot'u çalıştır"""
    bot = OBSBot()
    return await bot.run()
