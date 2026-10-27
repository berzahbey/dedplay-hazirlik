"""Bir kitabı işler: Stüdyo'nun okuma ve temizlik kodu (kutuphane.kaynak.cevir) -> kitap.json -> temiz EPUB + rapor.

Kod Stüdyo'dakiyle AYNI (kopya değil, kurulu dedplay-studyo deposundan içe aktarılır); burada yalnız sonuç dosyalarının
yeri ve adı Mac'e göre. Osmanlıca, PDF/DOCX ve seslendirme burada yapılmaz (Stüdyo'nun işi)."""
import os
import shutil
import time

from . import ayar  # noqa: F401  (ortam Stüdyo kodundan önce)


def _kod():
    from kutuphane import cikti, epubcheck, kaynak
    from kutuphane import epub as EPUB
    from kutuphane import kitap as K
    from kutuphane import rapor as R
    return kaynak, R, K, EPUB, epubcheck, cikti


def epub_dilleri(kit):
    """Kitabın kendi dilindeki tek EPUB: Türkçe varsa Türkçe, yoksa asıl dil (Stüdyo depo.surumler'in ilk sürümü)."""
    from kutuphane import kitap as K
    d = K.diller(kit)
    if "tr" in d:
        return ["tr"]
    asil = kit["kunye"].get("asil_dil", "tr")
    return [asil] if asil in d else sorted(d)[:1]


def _bos_ad(klasor, ad, uzanti, kid, onceki=None):
    """Temiz/ ve Rapor/ içinde başka kitabın dosyasını ezmeyen ad. Aynı kitabın önceki çıktısı (onceki) üzerine yazılır."""
    hedef = klasor / f"{ad}{uzanti}"
    if hedef.exists() and str(hedef) != (onceki or ""):
        hedef = klasor / f"{ad} ({kid[-6:]}){uzanti}"
    return hedef


def isle(kid, yol, ilerleme=None, onceki=None):
    """yol: Gelen/ içindeki kitap dosyası. Dönüş: {epub, rapor, baslik, yazar, denetim, ozet, sure}.
    onceki: aynı kitabın önceki sonucu (yeniden işlemede dosya adları korunur)."""
    kaynak, R, K, EPUB, epubcheck, cikti = _kod()
    onceki = onceki or {}
    t0 = time.time()
    klasor = ayar.KITAPLAR / kid
    klasor.mkdir(parents=True, exist_ok=True)
    kit = kaynak.cevir(str(yol), ilerleme, {"yol": str(yol)}, kapak_yolu=str(klasor / "kapak"))
    rapor = R.al()
    R.kaydet(str(klasor), rapor)
    kj = klasor / "kitap.json"
    if kj.exists():
        shutil.copy2(kj, str(kj) + ".yedek")
    K.kaydet(kit, str(kj))
    sorunlar = K.denetle(kit)
    if sorunlar:
        raise ValueError("kitap.json yapısal hata: " + "; ".join(sorunlar[:5]))

    if ilerleme:
        ilerleme("EPUB üretiliyor")
    diller = epub_dilleri(kit)
    kapak = None
    if kit["kunye"].get("kapak") and (klasor / kit["kunye"]["kapak"]).exists():
        kapak = (klasor / kit["kunye"]["kapak"]).read_bytes()
    gecici = klasor / "temiz.epub"
    EPUB.uret(kit, diller, str(gecici), kapak_png=kapak)
    if ilerleme:
        ilerleme("EPUB denetleniyor")
    denetim = epubcheck.denetle(str(gecici))

    ad = cikti.dosya_adi(kit)
    ayar.TEMIZ.mkdir(parents=True, exist_ok=True)
    ayar.RAPOR.mkdir(parents=True, exist_ok=True)
    epub_hedef = _bos_ad(ayar.TEMIZ, ad, ".epub", kid, onceki.get("epub"))
    rapor_hedef = _bos_ad(ayar.RAPOR, ad, ".txt", kid, onceki.get("rapor"))
    for eski, yeni in ((onceki.get("epub"), epub_hedef), (onceki.get("rapor"), rapor_hedef)):
        if eski and eski != str(yeni) and os.path.exists(eski):   # kitabın adı değiştiyse eski çıktısı kalkar
            os.remove(eski)
    shutil.copy2(gecici, str(epub_hedef) + ".tmp")
    os.replace(str(epub_hedef) + ".tmp", epub_hedef)
    rapor_metni = R.metin_hali(rapor) if rapor else "Rapor üretilemedi.\n"
    ust = [f"Dedplay Hazırlık raporu — {ad}",
           f"kaynak: {yol}",
           f"EPUB: {epub_hedef.name} ({', '.join(diller)}), epubcheck: "
           + ("kurulu değil" if denetim.get("hata") is None else f"{denetim['hata']} hata, {denetim['uyari']} uyarı"),
           f"süre: {time.time() - t0:.0f} sn", ""]
    rapor_hedef.write_text("\n".join(ust) + rapor_metni, encoding="utf-8")

    ku = kit["kunye"]
    gor = K.gorunur(kit)["bloklar"]
    ozet = {
        "sayfa": (ku.get("cikarma") or {}).get("sayfa"),
        "ocr_sayfa": (ku.get("cikarma") or {}).get("ocr"),
        "paragraf": sum(1 for b in gor if b["tur"] == "p"),
        "baslik": sum(1 for b in gor if b["tur"] == "baslik"),
        "dipnot": len(kit.get("dipnotlar") or {}),
    }
    return {"epub": str(epub_hedef), "rapor": str(rapor_hedef),
            "baslik": ku["baslik"].get("tr") or ku["baslik"].get(ku.get("asil_dil", "tr")) or ad,
            "yazar": ku.get("yazar", {}).get("tr") or "",
            "denetim": {"hata": denetim.get("hata"), "uyari": denetim.get("uyari")},
            "ozet": ozet, "sure": round(time.time() - t0)}
