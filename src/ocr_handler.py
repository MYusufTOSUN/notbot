"""
OCR İşleyici Modülü (EasyOCR + OpenCV)
Captcha görsellerini işler ve EasyOCR ile metne dönüştürür.
Derin öğrenme tabanlıdır, çizgili ve gürültülü captchaları çözmekte üstündür.
"""

import io
import os
import cv2
import numpy as np
import easyocr
from pathlib import Path
from src.logger import log_info, log_error, log_debug

# EasyOCR Reader'ı global olarak bir kere yükleyelim (Performans için)
# Sadece rakam okuyacak şekilde yapılandıracağız, ama EasyOCR'da whitelist parametresi read metodunda verilir.
# GPU varsa kullanır, yoksa CPU.
READER = None

def get_reader():
    global READER
    if READER is None:
        log_info("EasyOCR modeli yükleniyor... (Bu işlem ilk seferde biraz sürebilir)")
        # 'en' (English) modelini kullanıyoruz çünkü rakamlar evrensel
        READER = easyocr.Reader(['en'], gpu=False, verbose=False)
    return READER

class OCRHandler:
    """Captcha görsellerini EasyOCR ve OpenCV ile işleyen sınıf."""
    
    def __init__(self):
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.reader = get_reader()
    
    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """
        Görüntüyü OpenCV ile agresif şekilde temizle.
        Çizgileri kaldırmak için morfolojik işlemler uygula.
        """
        try:
            # Bytes -> Numpy Array -> OpenCV Image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # 1. Gri tonlama ve Ters Çevirme (Rakamlar genelde koyu, arka plan açık)
            # Thresholding işlemleri genelde beyaz üzerine siyah veya tam tersi daha iyi çalışır.
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 2. Thresholding (Adaptive yerine standart Otsu daha iyi olabilir çizgiler için)
            # Binary image: Siyah ve Beyaz
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # 3. Çizgi Temizleme (Morphological Opening)
            # Rakamlar kalın, çizgiler incedir. kernel boyutu çizgiyi yutacak kadar büyük,
            # ama rakamı bozmayacak kadar küçük olmalı.
            # (2,2) veya (3,3) kernel genelde iş görür.
            kernel = np.ones((2, 2), np.uint8)
            opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
            
            # 4. Parazit Temizleme (Median Blur)
            # Tuz-biber gürültüsünü alır
            denoised = cv2.medianBlur(opening, 3)
            
            # 5. Genişletme (Dilation)
            # Opening işlemi rakamları biraz inceltmiş olabilir, geri kalınlaştıralım.
            dilated = cv2.dilate(denoised, kernel, iterations=1)
            
            # 6. Ters çevir (Beyaz üzerine siyah yazı formatına geri dön - EasyOCR bunu sever)
            final_img = cv2.bitwise_not(dilated)
            
            # Debug için kaydet
            cv2.imwrite(str(self.temp_dir / "processed_easyocr.png"), final_img)
            log_debug("OpenCV ön işleme tamamlandı (Çizgi kaldırma uygulandı)")
            
            return final_img
            
        except Exception as e:
            log_error(f"Görüntü ön işleme hatası: {e}")
            raise
    
    def extract_text(self, image_bytes: bytes) -> str:
        """EasyOCR ile metin çıkar."""
        try:
            # Görüntüyü işle
            processed_img = self.preprocess_image(image_bytes)
            
            # EasyOCR ile oku
            # allowlist='0123456789' -> Sadece rakamları tanı
            try:
                results = self.reader.readtext(processed_img, allowlist='0123456789', detail=0)
            except TypeError:
                # Bazı eski sürümlerde allowlist parametresi farklı olabilir
                results = self.reader.readtext(processed_img, detail=0)
            
            # Sonuçları birleştir
            text = "".join(results)
            
            # Sadece rakamları al
            import re
            numbers_only = re.sub(r'[^0-9]', '', text)
            
            log_info(f"EasyOCR Sonucu: '{numbers_only}'")
            return numbers_only
            
        except Exception as e:
            log_error(f"EasyOCR hatası: {e}")
            return ""

    def extract_with_retry(self, image_bytes: bytes, expected_length: int = 4) -> str:
        """
        Farklı ön işleme yöntemleriyle dene.
        """
        # 1. Yöntem: Agresif Çizgi Kaldırma
        result = self.extract_text(image_bytes)
        if result and len(result) == expected_length:
            return result
        
        # 2. Yöntem: Sadece Threshold (Belki çizgiler rakamın bir parçası gibidir)
        try:
            log_debug("İlk deneme başarısız, alternatif işleme deneniyor...")
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
            
            results = self.reader.readtext(binary, allowlist='0123456789', detail=0)
            text = "".join(results)
            import re
            numbers_only = re.sub(r'[^0-9]', '', text)
            
            if numbers_only and len(numbers_only) == expected_length:
                log_info(f"Alternatif EasyOCR Sonucu: '{numbers_only}'")
                return numbers_only
                
        except Exception as e:
            log_error(f"Alternatif yöntem hatası: {e}")
            
        return result or ""
            
    def cleanup(self):
        """Geçici dosyaları temizle."""
        try:
            for file in self.temp_dir.glob("*"):
                file.unlink()
        except Exception:
            pass
