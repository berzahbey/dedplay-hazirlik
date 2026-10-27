"""Surya OCR hız ölçümü (Mac'te MPS / işlemci) ve sunucunun okumasıyla karşılaştırma.

Uygulamadaki "Ölçüm" düğmesi bunu ayrı bir süreçte çalıştırır (aygıt seçimi Surya yüklenmeden önce yapılmalı):
  python -m hazirlik.olcum <pdf> <ilk sayfa (1'den)> <adet> <mps|cpu> <çıktı.json>
OCR önbelleği kapalıdır (her sayfa gerçekten okunur). Karşılaştırma: sunucuda kaydedilen sayfa dökümü
(dokum_tahrif: araclar/sayfa_dokum.py kaydet) aynı PDF'in aynı sayfalarının satırlarını içerir; satırlar aynı
işlemden (kaynak._surya_satirlari) geçtiği için metinler doğrudan karşılaştırılabilir."""
import difflib
import glob
import gzip
import json
import os
import pickle
import sys
import tarfile
import time
import unicodedata

from . import ayar


def _ad(s):
    s = unicodedata.normalize("NFKD", os.path.basename(s or "")).lower()
    return "".join(c for c in s if c.isalnum())


def dokum_bul(pdf, sayfa_sayisi):
    """Bu PDF'in sunucudaki sayfa dökümü (kayıt sözlüğü) ya da None. ~/Dedplay/dokum_tahrif(.tgz) ve VERI/dokum aranır."""
    hedef = ayar.VERI / "dokum"
    for tgz in glob.glob(str(ayar.EV / "Dedplay" / "dokum_*.tgz")):
        isaret = hedef / (os.path.basename(tgz) + ".acildi")
        if not isaret.exists():
            hedef.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tgz) as t:
                uyeler = [m for m in t.getmembers() if m.isfile() and m.name.endswith(".pkl.gz") and ".." not in m.name]
                t.extractall(hedef, members=uyeler)
            isaret.write_text("")
    adaylar = glob.glob(str(hedef / "**" / "*.pkl.gz"), recursive=True)
    adaylar += glob.glob(str(ayar.EV / "Dedplay" / "dokum_*" / "*.pkl.gz"))
    pdf_ad = _ad(pdf)
    for d in adaylar:
        try:
            with gzip.open(d, "rb") as f:
                kayit = pickle.load(f)
        except Exception:
            continue
        if _ad(kayit.get("yol")) == pdf_ad and len(kayit.get("sayfalar") or []) == sayfa_sayisi:
            kayit["_dosya"] = d
            return kayit
    return None


def _metin(rows):
    return "\n".join(r["text"] for r in rows)


def karsilastir(okunan, kayit):
    """okunan: {pdf sayfa sırası: (satırlar, w, h)}. Sunucu kaydındaki aynı sayfalarla metin benzerliği."""
    kaynak = (kayit.get("bilgi") or {}).get("kaynak_sayfa") or [(i, None) for i in range(len(kayit["sayfalar"]))]
    sunucu = {}
    for j, (i, _) in enumerate(kaynak):
        sunucu.setdefault(i, []).extend(kayit["sayfalar"][j][0])
    sayfalar, ornek = [], []
    for i in sorted(okunan):
        a, b = _metin(okunan[i][0]), _metin(sunucu.get(i, []))
        oran = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if (a or b) else 1.0
        sayfalar.append({"sayfa": i + 1, "benzerlik": round(oran, 4), "ayni": a == b,
                         "satir_mac": len(okunan[i][0]), "satir_sunucu": len(sunucu.get(i, []))})
        if a != b and len(ornek) < 12:
            for d in difflib.unified_diff(b.splitlines(), a.splitlines(), lineterm="", n=0):
                if d[:1] in "+-" and not d.startswith(("+++", "---")):
                    ornek.append(f"s.{i + 1} {'sunucu' if d[0] == '-' else 'Mac   '}: {d[1:][:150]}")
                if len(ornek) >= 12:
                    break
    n = len(sayfalar) or 1
    return {"dokum": os.path.basename(kayit.get("_dosya", "")),
            "ortalama_benzerlik": round(sum(s["benzerlik"] for s in sayfalar) / n, 4),
            "birebir_ayni_sayfa": sum(1 for s in sayfalar if s["ayni"]),
            "en_farkli": sorted(sayfalar, key=lambda s: s["benzerlik"])[:5],
            "ornek_farklar": ornek}


def olc(pdf, ilk, adet, aygit, cikti):
    os.environ["OCR_ONBELLEK"] = "0"
    import fitz
    import torch
    from importlib.metadata import version
    from kutuphane import kaynak
    durum = {"pdf": pdf, "aygit": aygit, "basladi": time.time(), "asama": "model yükleniyor"}

    def yaz():
        with open(cikti + ".tmp", "w", encoding="utf-8") as f:
            json.dump(durum, f, ensure_ascii=False, indent=1)
        os.replace(cikti + ".tmp", cikti)
    yaz()
    sayfa_sayisi = len(fitz.open(pdf))
    sayfalar = [i for i in range(ilk - 1, ilk - 1 + adet) if 0 <= i < sayfa_sayisi]
    t0 = time.time()
    if not kaynak._surya_hazir():
        durum.update(asama="hata", hata="Surya yüklenemedi (modeller inmedi ya da kurulum eksik)")
        yaz()
        return durum
    durum.update(model_yukleme_sn=round(time.time() - t0, 1), asama="okunuyor",
                 surumler={"torch": torch.__version__, "surya": version("surya-ocr"),
                           "mps": bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())})
    yaz()
    okunan, sureler = {}, []
    for k in range(0, len(sayfalar), 4):          # Stüdyo da dörder sayfa okur
        parca = sayfalar[k:k + 4]
        t = time.time()
        okunan.update(kaynak._surya_sayfalar(pdf, parca))
        sureler.append((len(parca), time.time() - t))
        durum.update(okunan_sayfa=len(okunan), toplam_sayfa=len(sayfalar))
        yaz()
    toplam = sum(s for _, s in sureler)
    isinma = sureler[0][1] / sureler[0][0] if sureler else None
    kalan = sureler[1:]
    sn_sayfa = (sum(s for _, s in kalan) / sum(n for n, _ in kalan)) if kalan else isinma
    durum.update(asama="bitti", sayfalar=f"{sayfalar[0] + 1}-{sayfalar[-1] + 1}" if sayfalar else "",
                 okunamayan=[i + 1 for i in sayfalar if i not in okunan],
                 toplam_sn=round(toplam, 1), ilk_grup_sn_sayfa=round(isinma, 2) if isinma else None,
                 sn_sayfa=round(sn_sayfa, 2) if sn_sayfa else None,
                 kitap_tahmini_dk=round(sn_sayfa * sayfa_sayisi / 60) if sn_sayfa else None,
                 kitap_sayfa=sayfa_sayisi, bitti=time.time())
    kayit = dokum_bul(pdf, sayfa_sayisi)
    durum["karsilastirma"] = karsilastir(okunan, kayit) if kayit else None
    yaz()
    return durum


def metin_hali(sonuclar):
    s = [f"Dedplay Hazırlık — Surya hız ölçümü ({time.strftime('%d.%m.%Y %H:%M')})"]
    for d in sonuclar:
        s.append("")
        sv = d.get("surumler") or {}
        s.append(f"== {os.path.basename(d.get('pdf', ''))} — aygıt: {d.get('aygit')}"
                 + (f"  (torch {sv.get('torch')}, surya {sv.get('surya')}, MPS {'var' if sv.get('mps') else 'yok'})" if sv else ""))
        if d.get("asama") != "bitti":
            s.append(f"  bitmedi: {d.get('asama')} {d.get('hata', '')}")
            continue
        s.append(f"  sayfalar {d['sayfalar']}: toplam {d['toplam_sn']} sn; model yükleme {d.get('model_yukleme_sn')} sn")
        s.append(f"  ilk 4 sayfa (ısınma) {d['ilk_grup_sn_sayfa']} sn/sayfa; sonrası {d['sn_sayfa']} sn/sayfa")
        s.append(f"  bütün kitabın OCR'ı ({d['kitap_sayfa']} sayfa) tahmini: ~{d['kitap_tahmini_dk']} dk")
        if d.get("okunamayan"):
            s.append(f"  OKUNAMAYAN sayfalar: {d['okunamayan']}")
        k = d.get("karsilastirma")
        if not k:
            s.append("  sunucu kaydı (dokum) bulunamadı: karşılaştırma yok")
            continue
        s.append(f"  sunucu okumasıyla benzerlik: ortalama {k['ortalama_benzerlik']}, birebir aynı sayfa "
                 f"{k['birebir_ayni_sayfa']}  (kayıt: {k['dokum']})")
        for p in k["en_farkli"]:
            s.append(f"    s.{p['sayfa']}: {p['benzerlik']} (satır Mac {p['satir_mac']} / sunucu {p['satir_sunucu']})")
        for o in k["ornek_farklar"]:
            s.append(f"    {o}")
    return "\n".join(s) + "\n"


if __name__ == "__main__":
    pdf, ilk, adet, aygit, cikti = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
    olc(pdf, ilk, adet, aygit, cikti)
