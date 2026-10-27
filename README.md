# Dedplay Hazırlık (Mac Stüdyo)

<img src="icon.png" width="140" alt="Dedplay Hazırlık simgesi">

Kitapları **Mac'te** (Apple Silicon) OCR'dan geçirip temizler ve **temiz EPUB** üretir. Temiz EPUB sunucudaki
[Dedplay Stüdyo](https://github.com/berzahbey/dedplay-studyo)'ya gider; Stüdyo yalnız Osmanlıca, biçimler ve seslendirme yapar.

- Okuma ve temizlik kodu **Stüdyo'nun kendisi**: kurulum `berzahbey/dedplay-studyo` deposunu indirir ve `kutuphane.kaynak`
  aynen kullanılır (kopya yok, ortak kod tek yerde). Aynı kod ve veriyle Mac'te çıkan `kitap.json` sunucudakiyle birebir aynı.
- OCR: Surya 0.14.7, Apple ekran kartında (MPS). Tesseract ve Java (epubcheck) uygulamanın kendi klasöründe.
- Terminal yok: tarayıcıda açılan sayfa, Dock'ta **Dedplay Hazırlık** simgesi, sayfada **Güncelle** düğmesi.

## Kurulum (bir kez)

Terminal'i aç, şu satırı yapıştır, Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/berzahbey/dedplay-hazirlik/main/kur.sh | bash
```

İlk kurulum 10–20 dakika sürer (Python kütüphaneleri ~1 GB, Surya modelleri ~1,5 GB). Yönetici şifresi istemez.
Bitince sayfa kendiliğinden açılır; sonra Dock'taki simgeyle açılır.

Kurulanlar:

| Yer | İçerik |
|---|---|
| `~/Dedplay/Hazırlık/Gelen` | Kitapların girdiği klasör (sürükle-bırak da buraya yazar; alt klasörler de okunur) |
| `~/Dedplay/Hazırlık/Temiz` | Temiz EPUB'lar |
| `~/Dedplay/Hazırlık/Rapor` | Kitap raporları ve hız ölçümleri |
| `~/Applications/Dedplay Hazırlık.app` | Dock simgesi (uygulamayı başlatır, tarayıcıyı açar) |
| `~/Library/Application Support/Dedplay Hazirlik/` | Kod, Python ortamı, modeller, OCR önbelleği, günlükler |

Kaldırmak için bu üç yeri (ve Dock simgesini) silmek yeter.

## Kullanım

1. **Kitap ekle:** PDF/EPUB/DOCX/TXT dosyasını ya da bütün bir klasörü sayfaya sürükle (ya da Gelen klasörüne koy).
2. Liste aşamaları gösterir: Sırada → OCR x/y → Hazır. Kitaplar sırayla işlenir; iş sürerken Mac uyumaz.
3. **Aç** temiz EPUB'u açar, **Rapor** kitap raporunu gösterir (değişiklikler, şüpheli kelimeler, silinenler).
4. **Hız ölçümü:** bir PDF seç; Surya sayfa başına süre ve (varsa `~/Dedplay/dokum_*.tgz` kaydıyla) sunucunun okumasıyla karşılaştırma.

## Geliştirme

```bash
# Linux/Mac, Surya olmadan (metin katmanlı PDF ve TXT ile):
HAZIRLIK_STUDYO_KOD=../dedplay-studyo python -m pytest -q tests/
```

Ortam değişkenleri: `HAZIRLIK_UYGULAMA`, `HAZIRLIK_KLASOR`, `HAZIRLIK_STUDYO_KOD`, `HAZIRLIK_PORT` (8071),
`HAZIRLIK_STUDYO_KAYNAK` (kur.sh: Stüdyo kodunu GitHub yerine bir klasörden al).
