"""
OCR İşleyici Modülü - Gelişmiş Captcha Çözücü
OpenCV ile profesyonel seviye görüntü işleme + EasyOCR ile metin tanıma.
Çizgili, gürültülü ve bozulmuş captchaları çözmekte uzmanlaşmıştır.
"""

import io
import os
import cv2
import numpy as np
import easyocr
import re
from pathlib import Path
from typing import Optional, List, Tuple
from src.logger import log_info, log_error, log_debug, log_warning

# EasyOCR Reader'ı global olarak bir kere yükleyelim (Performans için)
READER = None

def get_reader():
    global READER
    if READER is None:
        log_info("EasyOCR modeli yükleniyor... (Bu işlem ilk seferde biraz sürebilir)")
        READER = easyocr.Reader(['en'], gpu=False, verbose=False)
    return READER


class OCRHandler:
    """Gelişmiş Captcha Çözücü - OpenCV + EasyOCR"""
    
    def __init__(self):
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.reader = get_reader()
        self.debug_mode = True  # Debug görsellerini kaydet
    
    def _save_debug_image(self, name: str, img: np.ndarray):
        """Debug için görüntüyü kaydet."""
        if self.debug_mode:
            try:
                cv2.imwrite(str(self.temp_dir / f"{name}.png"), img)
            except:
                pass
    
    def _bytes_to_cv2(self, image_bytes: bytes) -> np.ndarray:
        """Bytes'ı OpenCV görüntüsüne çevir."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    
    def _remove_horizontal_lines(self, binary_img: np.ndarray) -> np.ndarray:
        """Yatay çizgileri tespit edip kaldır."""
        # Yatay çizgileri tespit etmek için yatay kernel
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        
        # Yatay çizgileri tespit et
        detected_lines = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
        
        # Tespit edilen çizgileri orijinalden çıkar
        result = cv2.subtract(binary_img, detected_lines)
        
        return result
    
    def _remove_vertical_lines(self, binary_img: np.ndarray) -> np.ndarray:
        """Dikey çizgileri tespit edip kaldır."""
        # Dikey çizgileri tespit etmek için dikey kernel
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        
        # Dikey çizgileri tespit et
        detected_lines = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
        
        # Tespit edilen çizgileri orijinalden çıkar
        result = cv2.subtract(binary_img, detected_lines)
        
        return result
    
    def _remove_diagonal_lines(self, binary_img: np.ndarray) -> np.ndarray:
        """Çapraz çizgileri kaldır (Hough Transform ile)."""
        result = binary_img.copy()
        
        # Çizgileri tespit et
        lines = cv2.HoughLinesP(binary_img, 1, np.pi/180, threshold=30, 
                                minLineLength=15, maxLineGap=5)
        
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                # Çizgiyi beyaza boya (kaldır)
                cv2.line(result, (x1, y1), (x2, y2), 0, 2)
        
        return result
    
    def _enhance_contrast(self, img: np.ndarray) -> np.ndarray:
        """Kontrastı artır - CLAHE algoritması."""
        if len(img.shape) == 3:
            # Renkli görüntü - LAB uzayına çevir
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        else:
            # Gri görüntü
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            return clahe.apply(img)
    
    def _remove_noise(self, img: np.ndarray) -> np.ndarray:
        """Gürültü temizle - Non-local means denoising."""
        if len(img.shape) == 3:
            return cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        else:
            return cv2.fastNlMeansDenoising(img, None, 10, 7, 21)
    
    def _remove_small_components(self, binary_img: np.ndarray, min_size: int = 50) -> np.ndarray:
        """Küçük bağlı bileşenleri (gürültü noktaları) kaldır."""
        # Bağlı bileşenleri bul
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
        
        # Yeni temiz görüntü
        result = np.zeros_like(binary_img)
        
        for i in range(1, num_labels):  # 0 arka plan
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= min_size:
                result[labels == i] = 255
        
        return result
    
    def _sharpen_image(self, img: np.ndarray) -> np.ndarray:
        """Görüntüyü keskinleştir."""
        kernel = np.array([[-1, -1, -1],
                          [-1,  9, -1],
                          [-1, -1, -1]])
        return cv2.filter2D(img, -1, kernel)
    
    def _resize_image(self, img: np.ndarray, scale: float = 2.0) -> np.ndarray:
        """Görüntüyü büyüt (OCR doğruluğu için)."""
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        return cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)
    
    def _strategy_aggressive_line_removal(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 1: Agresif çizgi kaldırma."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        self._save_debug_image("s1_01_resized", img)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Kontrast artır
        gray = self._enhance_contrast(gray)
        self._save_debug_image("s1_02_contrast", gray)
        
        # Gaussian blur
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Adaptive threshold
        binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)
        self._save_debug_image("s1_03_binary", binary)
        
        # Yatay çizgileri kaldır
        no_horizontal = self._remove_horizontal_lines(binary)
        self._save_debug_image("s1_04_no_horizontal", no_horizontal)
        
        # Dikey çizgileri kaldır
        no_vertical = self._remove_vertical_lines(no_horizontal)
        self._save_debug_image("s1_05_no_vertical", no_vertical)
        
        # Küçük gürültüleri kaldır
        cleaned = self._remove_small_components(no_vertical, min_size=30)
        self._save_debug_image("s1_06_cleaned", cleaned)
        
        # Morfolojik closing (boşlukları doldur)
        kernel = np.ones((2, 2), np.uint8)
        closed = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
        
        # Ters çevir (beyaz üzerine siyah)
        result = cv2.bitwise_not(closed)
        self._save_debug_image("s1_final", result)
        
        return result
    
    def _strategy_otsu_morphology(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 2: Otsu threshold + morfoloji."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Gürültü azalt
        denoised = cv2.medianBlur(gray, 3)
        
        # Otsu threshold
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        self._save_debug_image("s2_01_otsu", binary)
        
        # Opening (gürültü kaldır)
        kernel_small = np.ones((2, 2), np.uint8)
        opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_small, iterations=1)
        self._save_debug_image("s2_02_opened", opened)
        
        # Çizgileri kaldır
        no_lines = self._remove_horizontal_lines(opened)
        no_lines = self._remove_vertical_lines(no_lines)
        self._save_debug_image("s2_03_no_lines", no_lines)
        
        # Dilation (karakterleri güçlendir)
        kernel_dilate = np.ones((2, 2), np.uint8)
        dilated = cv2.dilate(no_lines, kernel_dilate, iterations=1)
        
        # Ters çevir
        result = cv2.bitwise_not(dilated)
        self._save_debug_image("s2_final", result)
        
        return result
    
    def _strategy_color_based(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 3: Renk tabanlı segmentasyon."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # HSV uzayına çevir
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Düşük saturasyon (gri tonlar - genelde çizgiler)
        # Yüksek saturasyon (renkli - genelde karakterler)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Kontrast artır
        enhanced = self._enhance_contrast(gray)
        self._save_debug_image("s3_01_enhanced", enhanced)
        
        # Keskinleştir
        sharpened = self._sharpen_image(enhanced)
        self._save_debug_image("s3_02_sharpened", sharpened)
        
        # Threshold
        _, binary = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        self._save_debug_image("s3_03_binary", binary)
        
        # Küçük gürültüleri kaldır
        cleaned = self._remove_small_components(binary, min_size=40)
        
        # Çizgileri kaldır
        no_lines = self._remove_horizontal_lines(cleaned)
        no_lines = self._remove_vertical_lines(no_lines)
        
        # Ters çevir
        result = cv2.bitwise_not(no_lines)
        self._save_debug_image("s3_final", result)
        
        return result
    
    def _strategy_edge_based(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 4: Kenar tabanlı işleme."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Gürültü azalt
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # Canny kenar tespiti
        edges = cv2.Canny(blurred, 50, 150)
        self._save_debug_image("s4_01_edges", edges)
        
        # Dilate (kenarları birleştir)
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)
        self._save_debug_image("s4_02_dilated", dilated)
        
        # Contorleri doldur
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros_like(dilated)
        cv2.drawContours(filled, contours, -1, 255, -1)
        self._save_debug_image("s4_03_filled", filled)
        
        # Küçük bileşenleri kaldır
        cleaned = self._remove_small_components(filled, min_size=50)
        
        # Ters çevir
        result = cv2.bitwise_not(cleaned)
        self._save_debug_image("s4_final", result)
        
        return result
    
    def _strategy_simple_threshold(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 5: Basit threshold (bazen en iyisi basit olan)."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Basit threshold denemeleri
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
        self._save_debug_image("s5_final", binary)
        
        return binary
    
    def _strategy_bilateral_filter(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 6: Bilateral filter + threshold."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # Bilateral filter (kenarları koruyarak blur)
        filtered = cv2.bilateralFilter(img, 9, 75, 75)
        self._save_debug_image("s6_01_bilateral", filtered)
        
        # Gri tonlama
        gray = cv2.cvtColor(filtered, cv2.COLOR_BGR2GRAY)
        
        # Otsu threshold
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self._save_debug_image("s6_02_binary", binary)
        
        # Çizgileri kaldır
        inverted = cv2.bitwise_not(binary)
        no_lines = self._remove_horizontal_lines(inverted)
        no_lines = self._remove_vertical_lines(no_lines)
        
        # Ters çevir
        result = cv2.bitwise_not(no_lines)
        self._save_debug_image("s6_final", result)
        
        return result
    
    def _strategy_morphological_gradient(self, image_bytes: bytes) -> np.ndarray:
        """Strateji 7: Morfolojik gradient."""
        img = self._bytes_to_cv2(image_bytes)
        
        # Büyüt
        img = self._resize_image(img, 2.0)
        
        # Gri tonlama
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Morfolojik gradient
        kernel = np.ones((3, 3), np.uint8)
        gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
        self._save_debug_image("s7_01_gradient", gradient)
        
        # Threshold
        _, binary = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        self._save_debug_image("s7_02_binary", binary)
        
        # Closing
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        # Küçük gürültüleri kaldır
        cleaned = self._remove_small_components(closed, min_size=30)
        
        # Ters çevir
        result = cv2.bitwise_not(cleaned)
        self._save_debug_image("s7_final", result)
        
        return result
    
    def _ocr_image(self, img: np.ndarray) -> str:
        """EasyOCR ile metni çıkar."""
        try:
            results = self.reader.readtext(img, allowlist='0123456789', detail=0)
            text = "".join(results)
            numbers_only = re.sub(r'[^0-9]', '', text)
            return numbers_only
        except Exception as e:
            log_error(f"OCR hatası: {e}")
            return ""
    
    def _validate_result(self, text: str, expected_length: int = 4) -> bool:
        """Sonuç geçerli mi kontrol et."""
        if not text:
            return False
        if len(text) != expected_length:
            return False
        if not text.isdigit():
            return False
        return True
    
    def extract_text(self, image_bytes: bytes) -> str:
        """Ana OCR metodu - tek strateji."""
        try:
            processed_img = self._strategy_aggressive_line_removal(image_bytes)
            result = self._ocr_image(processed_img)
            log_info(f"OCR Sonucu: '{result}'")
            return result
        except Exception as e:
            log_error(f"OCR hatası: {e}")
            return ""
    
    def extract_with_retry(self, image_bytes: bytes, expected_length: int = 4) -> str:
        """
        Tüm stratejileri dene, geçerli sonuç bulunca dur.
        En güvenilir captcha çözme metodu.
        """
        strategies = [
            ("Agresif Çizgi Kaldırma", self._strategy_aggressive_line_removal),
            ("Otsu + Morfoloji", self._strategy_otsu_morphology),
            ("Renk Tabanlı", self._strategy_color_based),
            ("Bilateral Filter", self._strategy_bilateral_filter),
            ("Basit Threshold", self._strategy_simple_threshold),
            ("Morfolojik Gradient", self._strategy_morphological_gradient),
            ("Kenar Tabanlı", self._strategy_edge_based),
        ]
        
        results = []
        
        for name, strategy in strategies:
            try:
                log_debug(f"Strateji deneniyor: {name}")
                processed_img = strategy(image_bytes)
                result = self._ocr_image(processed_img)
                
                if self._validate_result(result, expected_length):
                    log_info(f"✓ Captcha çözüldü ({name}): {result}")
                    return result
                
                if result:
                    results.append((name, result))
                    log_debug(f"  Sonuç: '{result}' (uzunluk: {len(result)})")
                    
            except Exception as e:
                log_error(f"Strateji hatası ({name}): {e}")
                continue
        
        # Hiçbir strateji tam sonuç vermediyse, en yakın olanı seç
        if results:
            # En uzun ve expected_length'e en yakın olanı seç
            best_result = min(results, key=lambda x: abs(len(x[1]) - expected_length))
            name, text = best_result
            
            # Eğer sonuç uzunsa, son expected_length karakteri al
            if len(text) > expected_length:
                text = text[-expected_length:]
            
            log_warning(f"Kesin sonuç bulunamadı, en iyi tahmin ({name}): {text}")
            return text
        
        log_error("Hiçbir strateji sonuç üretemedi!")
        return ""
    
    def cleanup(self):
        """Geçici dosyaları temizle."""
        try:
            for file in self.temp_dir.glob("*.png"):
                file.unlink()
        except Exception:
            pass


# Test fonksiyonu
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        
        handler = OCRHandler()
        result = handler.extract_with_retry(image_bytes)
        print(f"\n{'='*50}")
        print(f"SONUÇ: {result}")
        print(f"{'='*50}")
    else:
        print("Kullanım: python ocr_handler.py <captcha_resmi.png>")
