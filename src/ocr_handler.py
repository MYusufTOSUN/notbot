"""
OCR İşleyici Modülü
Captcha görsellerini işler ve Tesseract OCR ile metne dönüştürür.
"""

import io
import re
from pathlib import Path
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
import pytesseract
from src.config import OCR_CONFIG, PROJECT_ROOT
from src.logger import log_info, log_error, log_debug


class OCRHandler:
    """Captcha görsellerini OCR ile işleyen sınıf."""
    
    def __init__(self):
        self.config = OCR_CONFIG
        self.temp_dir = PROJECT_ROOT / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Windows için Tesseract yolunu otomatik bul
        self._setup_tesseract_path()
    
    def _setup_tesseract_path(self):
        """Windows için Tesseract yolunu bul ve ayarla"""
        import sys
        import shutil
        
        if sys.platform.startswith('win'):
            # Eğer PATH'de yoksa yaygın yollara bak
            if not shutil.which("tesseract"):
                common_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                    r"C:\Users\tosun\AppData\Local\Tesseract-OCR\tesseract.exe"
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        pytesseract.pytesseract.tesseract_cmd = path
                        log_info(f"Tesseract bulundu: {path}")
                        return
                log_error("Tesseract.exe bulunamadı! Lütfen Tesseract OCR'ı kurun.")
    
    def preprocess_image(self, image_bytes: bytes) -> Image.Image:
        """
        Görüntüyü OCR için optimize et (Çizgi ve gürültü temizleme).
        """
        try:
            # Bytes'tan Image nesnesine dönüştür
            image = Image.open(io.BytesIO(image_bytes))
            
            # RGB moduna çevir
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 1. Gri tonlama ve Kontrast
            gray = ImageOps.grayscale(image)
            enhancer = ImageEnhance.Contrast(gray)
            high_contrast = enhancer.enhance(3.0)  # Yüksek kontrast
            
            # 2. Boyut artırma (Daha net algılama için 2 kat)
            width, height = high_contrast.size
            upscaled = high_contrast.resize((width * 2, height * 2), Image.LANCZOS)
            
            # 3. Eşikleme (Threshold) - Siyah/Beyaz yap
            # Arka planı beyaz, yazıları siyah yap
            threshold_val = 160
            binary = upscaled.point(lambda p: 255 if p > threshold_val else 0)
            
            # 4. Gürültü ve İnce Çizgi Temizleme (Median Filter)
            # Bu filtre ince çizgileri ve tek tük pikselleri yok eder
            denoised = binary.filter(ImageFilter.MedianFilter(size=3))
            
            # 5. Keskinleştirme
            sharpness = ImageEnhance.Sharpness(denoised)
            final_image = sharpness.enhance(2.0)
            
            # Debug için kaydet
            debug_path = self.temp_dir / "processed_captcha.png"
            final_image.save(debug_path)
            
            return final_image
            
        except Exception as e:
            log_error(f"Görüntü ön işleme hatası: {e}")
            raise
    
    def extract_text(self, image_bytes: bytes) -> str:
        """Captcha görüntüsünden metin çıkar."""
        try:
            # Görüntüyü işle
            processed_image = self.preprocess_image(image_bytes)
            
            # Tesseract Ayarları (Sadece rakam)
            custom_config = r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789'
            
            # OCR uygula
            text = pytesseract.image_to_string(processed_image, config=custom_config)
            
            # Temizlik
            numbers = re.sub(r'[^0-9]', '', text)
            
            log_info(f"OCR sonucu: '{numbers}'")
            return numbers
            
        except pytesseract.TesseractNotFoundError:
            log_error("Tesseract OCR PROGRAMI YÜKLÜ DEĞİL!")
            log_error("Lütfen şuradan indirip kurun: https://github.com/UB-Mannheim/tesseract/wiki")
            return ""
        except Exception as e:
            log_error(f"OCR hatası: {e}")
            return ""

    def extract_with_retry(self, image_bytes: bytes, expected_length: int = 4) -> str:
        """Tek deneme yeterli, güçlü preprocess kullanıyoruz."""
        return self.extract_text(image_bytes)
            
    def cleanup(self):
        """Geçici dosyaları temizle."""
        try:
            for file in self.temp_dir.glob("*"):
                file.unlink()
        except Exception:
            pass
