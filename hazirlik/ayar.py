"""Klasörler ve ortam. Stüdyo kodu (kutuphane, app) bu modül yüklendikten SONRA içe aktarılmalı: ortam değişkenlerini
Stüdyo modülleri yüklenirken okur.

Mac'te:
  uygulama  ~/Library/Application Support/Dedplay Hazirlik/   (kod, Python ortamı, modeller, OCR önbelleği, iş kayıtları)
  kullanıcı ~/Dedplay/Hazırlık/{Gelen,Temiz,Rapor}             (Zahir'in gördüğü klasörler)
Sınamada HAZIRLIK_UYGULAMA ve HAZIRLIK_KLASOR başka yere çevrilir."""
import os
import sys
import unicodedata
from pathlib import Path

EV = Path.home()
UYGULAMA = Path(os.environ.get("HAZIRLIK_UYGULAMA") or EV / "Library" / "Application Support" / "Dedplay Hazirlik")
# macOS dosya adlarını NFD verebilir; klasör adı her yerde aynı (NFC) yazılır
KLASOR = Path(unicodedata.normalize("NFC", os.environ.get("HAZIRLIK_KLASOR") or str(EV / "Dedplay" / "Hazırlık")))
GELEN, TEMIZ, RAPOR = KLASOR / "Gelen", KLASOR / "Temiz", KLASOR / "Rapor"

KOD = UYGULAMA / "kod"
STUDYO_KOD = Path(os.environ.get("HAZIRLIK_STUDYO_KOD") or KOD / "studyo")
VERI = UYGULAMA / "veri"
KITAPLAR = VERI / "kitaplar"
DURUM = VERI / "durum.json"
OLCUM = VERI / "olcum"
GUNLUK = UYGULAMA / "gunluk"
PORT = int(os.environ.get("HAZIRLIK_PORT", "8071"))
UZANTILAR = (".pdf", ".epub", ".docx", ".txt")

# Stüdyo kodunun okuduğu ortam (Docker imajındaki karşılıkları: DATA_DIR=/data, FONT_DIR, EPUBCHECK, MODEL_CACHE_DIR ...)
_ORTAM = {
    "DATA_DIR": str(VERI),                                  # OCR ve Tesseract önbelleği: VERI/ocr_onbellek
    "KAYNAK_DIR": str(GELEN),
    "OCR_MOTORU": "surya",
    "MODEL_CACHE_DIR": str(UYGULAMA / "modeller" / "surya"),
    "TORCH_DEVICE": "mps" if sys.platform == "darwin" else "cpu",
    "PYTORCH_ENABLE_MPS_FALLBACK": "1",                     # MPS'te olmayan işlem işlemciye düşer (hata vermez)
    "FONT_DIR": str(UYGULAMA / "fontlar"),
    "EPUBCHECK": str(UYGULAMA / "epubcheck" / "epubcheck.jar"),
    "TR_KELIME": str(UYGULAMA / "veri-dosyalari" / "tr_kelime.txt"),
    "TESSDATA_PREFIX": str(UYGULAMA / "tessdata"),
    "PYTHONUNBUFFERED": "1",
}
for _k, _v in _ORTAM.items():
    os.environ.setdefault(_k, _v)
# Tesseract ve Java uygulamanın kendi ortamında (micromamba): PATH'e eklenir
_ARAC = UYGULAMA / "ortam" / "bin"
if _ARAC.is_dir() and str(_ARAC) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_ARAC}{os.pathsep}{os.environ.get('PATH', '')}"
if str(STUDYO_KOD) not in sys.path:
    sys.path.insert(0, str(STUDYO_KOD))


def klasorleri_kur():
    for k in (GELEN, TEMIZ, RAPOR, KITAPLAR, OLCUM, GUNLUK):
        k.mkdir(parents=True, exist_ok=True)


def studyo_surumu():
    """Kurulu Stüdyo kodunun sürümü (kutuphane/main.py'deki SURUM satırı; modül yüklenmez)."""
    try:
        for satir in (STUDYO_KOD / "kutuphane" / "main.py").read_text(encoding="utf-8").splitlines():
            if satir.startswith("SURUM"):
                return satir.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return "?"


def studyo_commit():
    try:
        return (STUDYO_KOD / ".commit").read_text().strip()[:7]
    except OSError:
        return ""
