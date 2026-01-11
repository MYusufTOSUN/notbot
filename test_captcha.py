#!/usr/bin/env python3
"""
Captcha OCR Test Scripti
Captcha çözücünün doğruluğunu test etmek için kullanılır.

Kullanım:
    python test_captcha.py <captcha_görseli.png>
    python test_captcha.py temp/captcha_original.png
"""

import sys
import os

# Proje kökünü path'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ocr_handler import OCRHandler


def test_single_image(image_path: str):
    """Tek bir captcha görselini test et."""
    print(f"\n{'='*60}")
    print(f"📷 Test Edilen Görsel: {image_path}")
    print(f"{'='*60}")
    
    if not os.path.exists(image_path):
        print(f"❌ Dosya bulunamadı: {image_path}")
        return None
    
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    
    handler = OCRHandler()
    result = handler.extract_with_retry(image_bytes, expected_length=4)
    
    print(f"\n{'='*60}")
    print(f"🎯 SONUÇ: {result if result else 'Çözülemedi'}")
    print(f"{'='*60}")
    
    # Debug görselleri hakkında bilgi
    print("\n📁 Debug görselleri 'temp/' klasörüne kaydedildi:")
    print("   - s1_*.png: Agresif Çizgi Kaldırma stratejisi")
    print("   - s2_*.png: Otsu + Morfoloji stratejisi")
    print("   - s3_*.png: Renk Tabanlı strateji")
    print("   - s4_*.png: Kenar Tabanlı strateji")
    print("   - s5_*.png: Basit Threshold stratejisi")
    print("   - s6_*.png: Bilateral Filter stratejisi")
    print("   - s7_*.png: Morfolojik Gradient stratejisi")
    
    return result


def interactive_test():
    """İnteraktif test modu."""
    print("\n" + "="*60)
    print("🔬 CAPTCHA OCR TEST MODU")
    print("="*60)
    print("\nBu mod, captcha görsellerini test etmenizi sağlar.")
    print("Captcha görselini 'temp/' klasörüne koyun ve test edin.")
    print("\nKomutlar:")
    print("  q - Çıkış")
    print("  [dosya_adı] - Belirtilen dosyayı test et")
    print("  Enter - temp/captcha_original.png dosyasını test et")
    
    handler = OCRHandler()
    
    while True:
        print("\n" + "-"*40)
        user_input = input("📷 Dosya adı (veya Enter): ").strip()
        
        if user_input.lower() == 'q':
            print("👋 Çıkış yapılıyor...")
            break
        
        if not user_input:
            image_path = "temp/captcha_original.png"
        else:
            image_path = user_input
            if not image_path.startswith("temp/") and not os.path.isabs(image_path):
                # temp klasöründe ara
                if os.path.exists(f"temp/{image_path}"):
                    image_path = f"temp/{image_path}"
        
        test_single_image(image_path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Komut satırından dosya verildi
        for image_path in sys.argv[1:]:
            test_single_image(image_path)
    else:
        # İnteraktif mod
        interactive_test()

