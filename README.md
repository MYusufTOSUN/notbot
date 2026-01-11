# 🎓 ÖBS Push Bot - Selçuk Üniversitesi

OCR destekli, bulut uyumlu Öğrenci Bilgi Sistemi (OBİS) not takip botu.

## ✨ Özellikler

- 🔐 **Otomatik Captcha Çözme**: Tesseract OCR ile güvenlik kodunu otomatik çözer
- 📊 **Not Takibi**: Notlarınızı periyodik olarak kontrol eder
- 📲 **Telegram Bildirimi**: Not değişikliğinde anında bildirim
- ☁️ **Bulut Uyumlu**: GitHub Actions ile ücretsiz çalışır (20 dk'da bir)
- 💾 **Esnek Depolama**: JSONBin.io, GitHub veya lokal kayıt

## 🚀 Kurulum

### 1. Python Bağımlılıklarını Yükle
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Tesseract OCR Yükle

**Windows (Chocolatey ile):**
```bash
choco install tesseract
```

**Windows (Manuel):**
https://github.com/UB-Mannheim/tesseract/wiki adresinden indir

**Linux:**
```bash
sudo apt install tesseract-ocr
```

### 3. Yapılandırma
`.env` dosyası zaten bilgilerinizle dolu:
- ÖBS URL: https://obis1.selcuk.edu.tr
- Öğrenci No: 233311028
- Telegram bildirimleri aktif

## 🏃 Çalıştırma

```bash
python main.py
```

## ☁️ GitHub Actions Kurulumu

1. Bu repoyu GitHub'a private olarak push edin
2. **Settings → Secrets → Actions** kısmına şunları ekleyin:
   - `OBS_USER`: Öğrenci numaranız
   - `OBS_PASS`: ÖBS şifreniz
   - `TELEGRAM_TOKEN`: Telegram bot token'ınız
   - `TELEGRAM_CHAT_ID`: Telegram chat ID'niz
   - `JSONBIN_KEY`: JSONBin.io API key'iniz
   - `JSONBIN_ID`: JSONBin.io Bin ID'niz

3. Actions her 20 dakikada bir otomatik çalışır!

## 📁 Dosya Yapısı

```
obispush/
├── .github/workflows/main.yml  ← Her 20 dk'da çalışır
├── src/
│   ├── bot.py                  ← Selçuk ÖBS bot
│   ├── ocr_handler.py          ← Captcha çözücü
│   ├── telegram_notifier.py    ← Telegram bildirimleri
│   ├── data_manager.py         ← Not kayıt/karşılaştırma
│   ├── logger.py               ← Log sistemi
│   └── config.py               ← Ayarlar
├── .env                        ← Gizli bilgiler (GitHub'a gitmez!)
├── main.py                     ← Ana giriş noktası
├── notlar.json                 ← Kayıtlı notlar
└── logs.txt                    ← Çalışma logları
```

## ⚠️ Güvenlik

- `.env` dosyası `.gitignore`'da, GitHub'a **ASLA** yüklenmez
- GitHub Actions için bilgileri **Secrets** olarak ekleyin
- Private repo kullanın

## 📝 Lisans

MIT License
