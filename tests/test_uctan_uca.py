"""Uçtan uca: sürükle-bırak (yükleme) -> sıra -> Stüdyo kodu -> temiz EPUB + rapor. OCR gerektirmeyen (metin katmanlı)
PDF ve TXT ile; Surya'sız da çalışır. Stüdyo kodu HAZIRLIK_STUDYO_KOD'dan (yoksa ../dedplay-studyo) alınır.
  HAZIRLIK_STUDYO_KOD=~/dedplay-studyo python -m pytest -q tests/test_uctan_uca.py"""
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
GECICI = Path(tempfile.mkdtemp(prefix="hazirlik-sina-"))
os.environ["HAZIRLIK_UYGULAMA"] = str(GECICI / "uyg")
os.environ["HAZIRLIK_KLASOR"] = str(GECICI / "Hazırlık")
os.environ.setdefault("HAZIRLIK_STUDYO_KOD", str(KOK.parent / "dedplay-studyo"))
os.environ["TORCH_DEVICE"] = "cpu"
_V = os.environ.get("HAZIRLIK_SINAMA_VERI")   # kurulumdaki gibi: fontlar/, veri-dosyalari/tr_kelime.txt, epubcheck/
if _V:
    os.environ.update(FONT_DIR=f"{_V}/fontlar", TR_KELIME=f"{_V}/veri-dosyalari/tr_kelime.txt",
                      EPUBCHECK=f"{_V}/epubcheck/epubcheck.jar")
sys.path.insert(0, str(KOK))

import fitz  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from hazirlik import ayar, sira  # noqa: E402
from hazirlik.sunucu import app  # noqa: E402

PARAGRAF = ("Bu kitap, sınama için yazılmış uydurma bir metindir. Her paragrafta birkaç cümle bulunur ve cümleler "
            "sayfa sonunda bölünmeden devam eder. Okuyucu, metnin temiz bir şekilde aktarıldığını görmelidir.")


def _yazi_tipi():
    for y in (os.path.join(os.environ.get("FONT_DIR", ""), "Amiri-Regular.ttf"), "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(y):
            return y
    raise RuntimeError("Türkçe harfli yazı tipi yok")


def _pdf(yol):
    """Metin katmanlı PDF (Türkçe harfler gerçek yazı tipiyle: katman iyi, OCR gerekmez)."""
    yt = _yazi_tipi()
    doc = fitz.open()
    for s in range(1, 5):
        sayfa = doc.new_page(width=420, height=595)
        sayfa.insert_font(fontname="yt", fontfile=yt)
        sayfa.insert_text((40, 40), "DENEME KİTABI", fontsize=8, fontname="yt")
        y = 80
        for p in range(4):
            kutu = fitz.Rect(40, y, 380, y + 90)
            sayfa.insert_textbox(kutu, f"{s}.{p + 1} " + PARAGRAF, fontsize=10, fontname="yt")
            y += 100
        sayfa.insert_text((200, 570), str(s), fontsize=8, fontname="yt")
    doc.set_metadata({"title": "Deneme Kitabı", "author": "Sınama Yazarı"})
    doc.save(yol)


def _bekle(c, n, sure=240):
    son = time.time() + sure
    while time.time() < son:
        ks = c.get("/api/durum").json()["kitaplar"]
        if len(ks) >= n and all(k["asama"] in ("hazir", "hata") for k in ks):
            return ks
        time.sleep(1)
    raise AssertionError("zaman aşımı: " + str(c.get("/api/durum").json()["kitaplar"]))


def test_uctan_uca():
    pdf = GECICI / "Sınama Yazarı - Deneme Kitabı.pdf"
    _pdf(pdf)
    with TestClient(app) as c:
        d = c.get("/api/durum").json()
        assert d["studyo_surum"] != "?"
        # sürükle-bırak: klasör yapısıyla
        r = c.post("/api/yukle", files={"dosya": (pdf.name, pdf.read_bytes())}, data={"yol": "Toplu/" + pdf.name})
        assert r.status_code == 200 and r.json()["kid"], r.text
        assert (ayar.GELEN / "Toplu" / pdf.name).exists()
        # aynı içerik ikinci kez eklenmez
        assert c.post("/api/yukle", files={"dosya": (pdf.name, pdf.read_bytes())}, data={"yol": pdf.name}).json()["zaten_var"]
        # Gelen klasörüne doğrudan konan dosya (iki taramada boyutu aynıysa) eklenir
        (ayar.GELEN / "ikinci.txt").write_text("BİRİNCİ BÖLÜM\n\n" + "\n\n".join([PARAGRAF] * 6), encoding="utf-8")
        sira.gelen_tara(); sira.gelen_tara()
        ks = _bekle(c, 2)
        assert all(k["asama"] == "hazir" for k in ks), [k.get("hata") for k in ks]
        for k in ks:
            assert Path(k["epub"]).parent == ayar.TEMIZ and Path(k["epub"]).exists()
            assert Path(k["rapor"]).parent == ayar.RAPOR and "Dedplay Hazırlık raporu" in Path(k["rapor"]).read_text("utf-8")
            with zipfile.ZipFile(k["epub"]) as z:
                metin = " ".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xhtml"))
            assert "uydurma bir metindir" in metin
            assert c.get(f"/api/kitap/{k['kid']}/rapor").status_code == 200
        pdf_kitap = next(k for k in ks if k["ad"].endswith(".pdf"))
        assert pdf_kitap["ozet"]["paragraf"] >= 4
        # yeniden işleme aynı dosya adlarını kullanır
        eski = pdf_kitap["epub"]
        assert c.post(f"/api/kitap/{pdf_kitap['kid']}/yeniden").status_code == 200
        ks = _bekle(c, 2)
        assert next(k for k in ks if k["kid"] == pdf_kitap["kid"])["epub"] == eski
        assert len(list(ayar.TEMIZ.glob("*.epub"))) == 2
        # listeden çıkan kitap Gelen'de dursa da geri gelmez
        assert c.post(f"/api/kitap/{pdf_kitap['kid']}/kaldir").status_code == 200
        sira._bilinen.clear(); sira._boyutlar.clear()
        sira.gelen_tara(); sira.gelen_tara()
        assert len(c.get("/api/durum").json()["kitaplar"]) == 1
        # elle yeniden sürüklenirse gelir
        assert c.post("/api/yukle", files={"dosya": (pdf.name, pdf.read_bytes())}, data={"yol": "Toplu/" + pdf.name}).json()["kid"]
