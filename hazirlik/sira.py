"""Kitap listesi ve arka plan sırası.

- Gelen/ klasörü (alt klasörleriyle) 10 sn'de bir taranır; boyutu iki taramada değişmeyen yeni dosya listeye eklenir.
  Aynı içerik (sha1) ikinci kez eklenmez. Sürükle-bırak da dosyayı Gelen/'e yazar, yani tek giriş yolu var.
- Tek iş parçacığı kitapları sırayla işler (Stüdyo kodu kitap başına genel durum tutar; aynı anda iki kitap işlenmez).
- İş sürerken Mac uyumaz (caffeinate -is); sıra boşalınca bırakılır.
- Durum VERI/durum.json'da; uygulama kapanıp açılınca yarım kalan kitap baştan sıraya girer (OCR önbellekten devam eder)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import unicodedata

from . import ayar

_kilit = threading.RLock()
_uyar = threading.Event()
_kitaplar = {}       # kid -> kayıt
_boyutlar = {}       # yol -> (boyut, mtime) son tarama
_bilinen = {}        # yol -> (boyut, mtime): bu imzayla zaten bakıldı
_kafein = None
_kaldirilan = set()  # listeden çıkarılan kitapların sha1'i: Gelen'de dursa da kendiliğinden geri eklenmez
_SAYFA = re.compile(r"sayfa (\d+)/(\d+)")


def _yaz():
    with _kilit:
        ayar.DURUM.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(ayar.DURUM) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"kitaplar": list(_kitaplar.values()), "kaldirilan": sorted(_kaldirilan)}, f,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, ayar.DURUM)


def yukle():
    with _kilit:
        _kitaplar.clear()
        _kaldirilan.clear()
        try:
            veri = json.load(open(ayar.DURUM, encoding="utf-8"))
            _kaldirilan.update(veri.get("kaldirilan", []))
            for k in veri.get("kitaplar", []):
                if k.get("asama") == "isleniyor":      # uygulama iş ortasında kapanmış
                    k.update(asama="sirada", mesaj="Yeniden sırada (uygulama kapanmıştı)")
                _kitaplar[k["kid"]] = k
        except (OSError, ValueError):
            pass


def liste():
    with _kilit:
        return sorted((dict(k) for k in _kitaplar.values()), key=lambda k: k.get("eklendi", 0), reverse=True)


def bul(kid):
    with _kilit:
        k = _kitaplar.get(kid)
        return dict(k) if k else None


def _guncelle(kid, **kw):
    with _kilit:
        if kid in _kitaplar:
            _kitaplar[kid].update(kw)
            _yaz()


def _sha1(yol):
    h = hashlib.sha1()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def _kimlik(yol, sha):
    ad = os.path.splitext(os.path.basename(yol))[0]
    ad = ad.translate(str.maketrans("İıŞşĞğÇçÖöÜü", "IiSsGgCcOoUu"))
    ad = "".join(c for c in unicodedata.normalize("NFKD", ad) if not unicodedata.combining(c))
    ad = re.sub(r"[^A-Za-z0-9]+", "-", ad).strip("-")[:60] or "kitap"
    return f"{ad}-{sha[:6]}"


def ekle(yol, elle=False):
    """Dosyayı listeye ekler (aynı içerik varsa eklemez). elle: sürükle-bırak (daha önce listeden çıkarılmış olsa da
    eklenir). Dönüş: kid ya da None."""
    yol = unicodedata.normalize("NFC", str(yol))
    sha = _sha1(yol)
    with _kilit:
        if sha in _kaldirilan:
            if not elle:
                return None
            _kaldirilan.discard(sha)
        for k in _kitaplar.values():
            if k.get("sha1") == sha:
                if k.get("yol") != yol and not os.path.exists(k.get("yol", "")):
                    k["yol"] = yol           # dosya Gelen içinde taşınmış
                    _yaz()
                return None
        kid = _kimlik(yol, sha)
        _kitaplar[kid] = {"kid": kid, "yol": yol, "sha1": sha, "ad": os.path.basename(yol),
                          "boyut": os.path.getsize(yol), "eklendi": time.time(), "asama": "sirada",
                          "mesaj": "Sırada", "ilerleme": None}
        _yaz()
    _uyar.set()
    return kid


def gelen_tara():
    """Gelen/ içindeki yeni ve kopyalanması bitmiş (iki taramada boyutu aynı) dosyalar listeye girer."""
    eklenen = []
    if not ayar.GELEN.is_dir():
        return eklenen
    for kok, klasorler, dosyalar in os.walk(ayar.GELEN):
        klasorler[:] = [d for d in klasorler if not d.startswith(".")]
        for ad in dosyalar:
            if ad.startswith(".") or not ad.lower().endswith(ayar.UZANTILAR) or ad.endswith(".yukleniyor"):
                continue
            yol = os.path.join(kok, ad)
            try:
                st = os.stat(yol)
            except OSError:
                continue
            imza = (st.st_size, st.st_mtime)
            if _boyutlar.get(yol) != imza:
                _boyutlar[yol] = imza          # bir sonraki taramada aynıysa kopyalama bitmiştir
                continue
            if yol in _bilinen and _bilinen[yol] == imza:
                continue
            _bilinen[yol] = imza                   # sha1 bir kez hesaplanır (büyük PDF'te her taramada değil)
            try:
                kid = ekle(yol)
                if kid:
                    eklenen.append(kid)
            except OSError:
                pass
    return eklenen


def yeniden(kid):
    with _kilit:
        k = _kitaplar.get(kid)
        if not k or k.get("asama") == "isleniyor":
            return False
        k.update(asama="sirada", mesaj="Sırada", hata=None, ilerleme=None)
        _yaz()
    _uyar.set()
    return True


def kaldir(kid):
    """Listeden çıkarır (Temiz/ ve Rapor/ dosyalarına, Gelen'deki asıl dosyaya dokunmaz). Gelen'de duran dosya
    kendiliğinden geri eklenmez; yeniden sürüklenirse eklenir."""
    with _kilit:
        k = _kitaplar.get(kid)
        if not k or k.get("asama") == "isleniyor":
            return False
        del _kitaplar[kid]
        _kaldirilan.add(k.get("sha1"))
        _yaz()
    shutil.rmtree(ayar.KITAPLAR / kid, ignore_errors=True)
    return True


# ---------------------------------------------------------------- işçi
def _uyanik(acik):
    global _kafein
    if acik and _kafein is None and shutil.which("caffeinate"):
        _kafein = subprocess.Popen(["caffeinate", "-is", "-w", str(os.getpid())])
    elif not acik and _kafein is not None:
        _kafein.terminate()
        _kafein = None


def _sonraki():
    with _kilit:
        bekleyen = [k for k in _kitaplar.values() if k.get("asama") == "sirada"]
        if not bekleyen:
            return None
        k = min(bekleyen, key=lambda k: k.get("eklendi", 0))
        k.update(asama="isleniyor", mesaj="Başlıyor", basladi=time.time(), hata=None, ilerleme=None)
        _yaz()
        return dict(k)


def _ilerleme_yaz(kid):
    son = [0.0]

    def ilerleme(mesaj):
        m = _SAYFA.search(mesaj or "")
        kw = {"mesaj": mesaj}
        if m:
            kw["ilerleme"] = [int(m.group(1)), int(m.group(2))]
        elif not (mesaj or "").startswith("OCR"):
            kw["ilerleme"] = None
        now = time.time()
        if now - son[0] > 1 or not m:            # sık yazma yok (sayfa başına bir kez yeter)
            son[0] = now
            _guncelle(kid, **kw)
        else:
            with _kilit:
                _kitaplar.get(kid, {}).update(kw)
    return ilerleme


def _is(k):
    from . import isle
    kid = k["kid"]
    if not os.path.exists(k["yol"]):
        _guncelle(kid, asama="hata", mesaj="Dosya Gelen klasöründe yok", hata="Dosya bulunamadı: " + k["yol"])
        return
    try:
        sonuc = isle.isle(kid, k["yol"], _ilerleme_yaz(kid), onceki={"epub": k.get("epub"), "rapor": k.get("rapor")})
        _guncelle(kid, asama="hazir", mesaj="Hazır", ilerleme=None, bitti=time.time(), **sonuc)
    except Exception as e:
        iz = traceback.format_exc()
        (ayar.KITAPLAR / kid).mkdir(parents=True, exist_ok=True)
        (ayar.KITAPLAR / kid / "hata.txt").write_text(iz, encoding="utf-8")
        _guncelle(kid, asama="hata", mesaj="Hata", ilerleme=None, hata=f"{type(e).__name__}: {str(e)[:300]}")


_ek_isler = []       # (ad, işlev): ölçüm gibi kitap dışı işler; kitaplarla aynı sırada (aynı anda OCR olmasın)


def ek_is(ad, islev):
    with _kilit:
        _ek_isler.append((ad, islev))
    _uyar.set()


def mesgul():
    with _kilit:
        return any(k.get("asama") == "isleniyor" for k in _kitaplar.values())


def _isci():
    while True:
        with _kilit:
            ek = _ek_isler.pop(0) if _ek_isler else None
        if ek:
            _uyanik(True)
            try:
                ek[1]()
            except Exception:
                traceback.print_exc()
            continue
        k = _sonraki()
        if k:
            _uyanik(True)
            _is(k)
            continue
        _uyanik(False)
        _uyar.wait(10)
        _uyar.clear()


def _tarayici():
    while True:
        try:
            gelen_tara()
        except Exception:
            traceback.print_exc()
        time.sleep(10 if not _boyutlar else 5)


def baslat():
    ayar.klasorleri_kur()
    yukle()
    for hedef in (_isci, _tarayici):
        threading.Thread(target=hedef, daemon=True).start()
