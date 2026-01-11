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
    
    def preprocess_image(self, image_bytes: bytes) -> Image.Image:
        """
        Görüntüyü OCR için optimize et.
        
        İşlem adımları:
        1. Gri tonlamaya çevir
        2. Kontrastı artır
        3. Eşikleme (threshold) uygula
        4. Gürültü azaltma
        5. Boyut artırma (upscale)
        """
        try:
            # Bytes'tan Image nesnesine dönüştür
            image = Image.open(io.BytesIO(image_bytes))
            
            # RGB moduna çevir (RGBA veya diğer modlardan)
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Gri tonlamaya çevir
            gray = ImageOps.grayscale(image)
            
            # Kontrastı artır
            enhancer = ImageEnhance.Contrast(gray)
            contrasted = enhancer.enhance(2.5)
            
            # Parlaklığı ayarla
            brightness = ImageEnhance.Brightness(contrasted)
            brightened = brightness.enhance(1.2)
            
            # Keskinleştir
            sharpness = ImageEnhance.Sharpness(brightened)
            sharpened = sharpness.enhance(2.0)
            
            # Boyutu 3 kat artır (küçük captchalar için)
            width, height = sharpened.size
            upscaled = sharpened.resize((width * 3, height * 3), Image.LANCZOS)
            
            # Eşikleme (Threshold) - siyah-beyaz yap
            threshold = 140
            binary = upscaled.point(lambda p: 255 if p > threshold else 0)
            
            # Gürültü azaltma
            denoised = binary.filter(ImageFilter.MedianFilter(size=3))
            
            log_debug("Görüntü ön işleme tamamlandı")
            return denoised
            
        except Exception as e:
            log_error(f"Görüntü ön işleme hatası: {e}")
            raise
    
    def extract_text(self, image_bytes: bytes) -> str:
        """
        Captcha görüntüsünden metin çıkar.
        
        Args:
            image_bytes: Captcha görüntüsünün bytes hali
            
        Returns:
            Çıkarılan metin (sadece rakamlar)
        """
        try:
            # Görüntüyü ön işle
            processed_image = self.preprocess_image(image_bytes)
            
            # Debug için işlenmiş görüntüyü kaydet
            debug_path = self.temp_dir / "processed_captcha.png"
            processed_image.save(debug_path)
            log_debug(f"İşlenmiş captcha kaydedildi: {debug_path}")
            
            # Tesseract ile OCR uygula
            text = pytesseract.image_to_string(
                processed_image,
                lang=self.config["lang"],
                config=self.config["config"]
            )
            
            # Sadece rakamları al ve temizle
            numbers_only = re.sub(r'[^0-9]', '', text.strip())
            
            log_info(f"OCR sonucu: '{numbers_only}' (Ham: '{text.strip()}')")
            return numbers_only
            
        except pytesseract.TesseractNotFoundError:
            log_error("Tesseract OCR yüklü değil! Lütfen Tesseract'ı yükleyin.")
            raise
        except Exception as e:
            log_error(f"OCR hatası: {e}")
            raise
    
    def extract_with_retry(self, image_bytes: bytes, expected_length: int = 4) -> str:
        """
        OCR'ı birden fazla ön işleme yöntemiyle dene.
        
        Args:
            image_bytes: Captcha görüntüsü
            expected_length: Beklenen karakter sayısı
            
        Returns:
            Çıkarılan metin
        """
        methods = [
            self._method_standard,
            self._method_high_contrast,
            self._method_inverted,
            self._method_adaptive
        ]
        
        for i, method in enumerate(methods):
            try:
                log_debug(f"OCR yöntemi {i+1}/{len(methods)} deneniyor...")
                result = method(image_bytes)
                
                if result and len(result) == expected_length:
                    log_info(f"OCR başarılı (yöntem {i+1}): {result}")
                    return result
                    
            except Exception as e:
                log_debug(f"Yöntem {i+1} başarısız: {e}")
                continue
        
        # Hiçbir yöntem doğru uzunlukta sonuç vermediyse, en iyi tahmini döndür
        log_debug("Tüm yöntemler denendi, standart sonuç döndürülüyor")
        return self.extract_text(image_bytes)
    
    def _method_standard(self, image_bytes: bytes) -> str:
        """Standart OCR yöntemi."""
        return self.extract_text(image_bytes)
    
    def _method_high_contrast(self, image_bytes: bytes) -> str:
        """Yüksek kontrast yöntemi."""
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        gray = ImageOps.grayscale(image)
        enhancer = ImageEnhance.Contrast(gray)
        high_contrast = enhancer.enhance(4.0)
        
        # Boyut artır
        width, height = high_contrast.size
        upscaled = high_contrast.resize((width * 4, height * 4), Image.LANCZOS)
        
        # Eşikleme
        binary = upscaled.point(lambda p: 255 if p > 100 else 0)
        
        text = pytesseract.image_to_string(
            binary,
            config=self.config["config"]
        )
        return re.sub(r'[^0-9]', '', text.strip())
    
    def _method_inverted(self, image_bytes: bytes) -> str:
        """Ters çevrilmiş görüntü yöntemi."""
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        gray = ImageOps.grayscale(image)
        inverted = ImageOps.invert(gray)
        
        width, height = inverted.size
        upscaled = inverted.resize((width * 3, height * 3), Image.LANCZOS)
        
        text = pytesseract.image_to_string(
            upscaled,
            config=self.config["config"]
        )
        return re.sub(r'[^0-9]', '', text.strip())
    
    def _method_adaptive(self, image_bytes: bytes) -> str:
        """Adaptif eşikleme yöntemi."""
        try:
            import cv2
            import numpy as np
            
            # Bytes'tan numpy array'e
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Gri tonlama
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Adaptif eşikleme
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, 11, 2
            )
            
            # Gürültü azaltma
            denoised = cv2.medianBlur(thresh, 3)
            
            # Boyut artır
            upscaled = cv2.resize(denoised, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            
            # PIL Image'a dönüştür
            pil_image = Image.fromarray(upscaled)
            
            text = pytesseract.image_to_string(
                pil_image,
                config=self.config["config"]
            )
            return re.sub(r'[^0-9]', '', text.strip())
            
        except ImportError:
            log_debug("OpenCV bulunamadı, adaptif yöntem atlanıyor")
            return ""
    
    def cleanup(self):
        """Geçici dosyaları temizle."""
        try:
            for file in self.temp_dir.glob("*"):
                file.unlink()
            log_debug("Geçici dosyalar temizlendi")
        except Exception as e:
            log_debug(f"Temizlik hatası: {e}")
