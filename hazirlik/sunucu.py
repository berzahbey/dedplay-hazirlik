"""Dedplay Hazırlık: tarayıcıda açılan sayfa (yalnız bu Mac'ten: 127.0.0.1).
  uvicorn hazirlik.sunucu:app --host 127.0.0.1 --port 8071"""
import json
import os
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from . import SURUM, ayar, olcum, sira

app = FastAPI(title="Dedplay Hazırlık")
STATIC = Path(__file__).parent / "static"
_guncelleme = {"durum": None, "mesaj": "", "zaman": None}
_olcum = {"durum": None}


@app.on_event("startup")
def _basla():
    sira.baslat()


@app.get("/")
def ana():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/simge.png")
def simge():
    yol = Path(__file__).parents[1] / "icon.png"
    if not yol.exists():
        raise HTTPException(404)
    return FileResponse(yol)


def _aygit():
    """Surya hangi aygıtta çalışacak (torch yüklemeden: ortam değişkeni)."""
    return os.environ.get("TORCH_DEVICE", "cpu")


@app.get("/api/durum")
def durum():
    return {"surum": SURUM, "studyo_surum": ayar.studyo_surumu(), "studyo_commit": ayar.studyo_commit(),
            "aygit": _aygit(), "kitaplar": sira.liste(),
            "klasorler": {"gelen": str(ayar.GELEN), "temiz": str(ayar.TEMIZ), "rapor": str(ayar.RAPOR)},
            "guncelleme": _guncelleme, "olcum": _olcum, "mac": sys.platform == "darwin"}


def _guvenli_yol(goreli):
    """Sürüklenen dosyanın Gelen/ altındaki yolu (klasör yapısı korunur; dışarı çıkamaz)."""
    parcalar = [p for p in unicodedata.normalize("NFC", goreli or "").replace("\\", "/").split("/")
                if p not in ("", ".", "..") and not p.startswith(".")]
    if not parcalar:
        raise HTTPException(400, "Dosya adı yok")
    hedef = ayar.GELEN.joinpath(*parcalar).resolve()
    if ayar.GELEN.resolve() not in hedef.parents:
        raise HTTPException(400, "Geçersiz yol")
    return hedef


@app.post("/api/yukle")
async def yukle(dosya: UploadFile = File(...), yol: str = Form("")):
    """Sürükle-bırak: dosya Gelen/'e yazılır (klasör bırakıldıysa alt klasörüyle) ve hemen listeye eklenir."""
    goreli = yol or dosya.filename
    if not goreli.lower().endswith(ayar.UZANTILAR):
        return {"atlandi": goreli, "neden": "desteklenmeyen tür (PDF, EPUB, DOCX, TXT)"}
    hedef = _guvenli_yol(goreli)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_name(hedef.name + ".yukleniyor")
    with open(gecici, "wb") as f:
        while parca := await dosya.read(1 << 20):
            f.write(parca)
    if hedef.exists():   # aynı adda dosya: içerik aynıysa üzerine, değilse yeni ad
        if sira._sha1(gecici) != sira._sha1(hedef):
            k = 2
            while hedef.with_name(f"{hedef.stem} ({k}){hedef.suffix}").exists():
                k += 1
            hedef = hedef.with_name(f"{hedef.stem} ({k}){hedef.suffix}")
    os.replace(gecici, hedef)
    kid = sira.ekle(hedef, elle=True)
    return {"kid": kid, "yol": str(hedef), "zaten_var": kid is None}


def _kitap(kid):
    k = sira.bul(kid)
    if not k:
        raise HTTPException(404, "Kitap bulunamadı")
    return k


def _ac(*arg):
    if sys.platform != "darwin":
        raise HTTPException(400, "Yalnız Mac'te açılır")
    subprocess.Popen(["open", *arg])


@app.post("/api/kitap/{kid}/ac")
def ac(kid: str):
    k = _kitap(kid)
    if not k.get("epub") or not os.path.exists(k["epub"]):
        raise HTTPException(404, "Temiz EPUB yok")
    _ac(k["epub"])
    return {"ok": True}


@app.post("/api/kitap/{kid}/goster")
def goster(kid: str):
    k = _kitap(kid)
    yol = k.get("epub") if k.get("epub") and os.path.exists(k["epub"]) else k.get("yol")
    _ac("-R", yol)
    return {"ok": True}


@app.get("/api/kitap/{kid}/rapor", response_class=PlainTextResponse)
def rapor(kid: str):
    k = _kitap(kid)
    if k.get("rapor") and os.path.exists(k["rapor"]):
        return Path(k["rapor"]).read_text(encoding="utf-8")
    hata = ayar.KITAPLAR / kid / "hata.txt"
    if hata.exists():
        return "HATA\n\n" + hata.read_text(encoding="utf-8")
    raise HTTPException(404, "Rapor yok")


@app.post("/api/kitap/{kid}/yeniden")
def yeniden(kid: str):
    if not sira.yeniden(kid):
        raise HTTPException(409, "Kitap işleniyor ya da yok")
    return {"ok": True}


@app.post("/api/kitap/{kid}/kaldir")
def kaldir(kid: str):
    if not sira.kaldir(kid):
        raise HTTPException(409, "Kitap işleniyor ya da yok")
    return {"ok": True}


@app.post("/api/klasor/{ad}")
def klasor(ad: str):
    yol = {"gelen": ayar.GELEN, "temiz": ayar.TEMIZ, "rapor": ayar.RAPOR}.get(ad)
    if not yol:
        raise HTTPException(404)
    yol.mkdir(parents=True, exist_ok=True)
    _ac(str(yol))
    return {"ok": True}


# ---------------------------------------------------------------- ölçüm
def _olcum_isi(pdf, ilk, adet, cpu_adet):
    sonuclar = []
    calisma = [("mps" if sys.platform == "darwin" else "cpu", adet)]
    if cpu_adet and sys.platform == "darwin":
        calisma.append(("cpu", cpu_adet))
    ayar.OLCUM.mkdir(parents=True, exist_ok=True)
    for aygit, n in calisma:
        cikti = str(ayar.OLCUM / f"{time.strftime('%Y%m%d-%H%M%S')}-{aygit}.json")
        _olcum.update(durum="calisiyor", aygit=aygit, cikti=cikti, mesaj=f"{aygit}: model yükleniyor")
        ortam = dict(os.environ, TORCH_DEVICE=aygit)
        with open(ayar.GUNLUK / "olcum.log", "a", encoding="utf-8") as g:
            p = subprocess.Popen([sys.executable, "-m", "hazirlik.olcum", pdf, str(ilk), str(n), aygit, cikti],
                                 cwd=str(Path(__file__).parents[1]), env=ortam, stdout=g, stderr=subprocess.STDOUT)
            while p.poll() is None:
                time.sleep(2)
                try:
                    d = json.load(open(cikti, encoding="utf-8"))
                    _olcum["mesaj"] = f"{aygit}: {d.get('asama')} {d.get('okunan_sayfa', 0)}/{d.get('toplam_sayfa', n)}"
                except (OSError, ValueError):
                    pass
        try:
            sonuclar.append(json.load(open(cikti, encoding="utf-8")))
        except (OSError, ValueError):
            sonuclar.append({"pdf": pdf, "aygit": aygit, "asama": "hata", "hata": "sonuç yazılmadı (günlük: olcum.log)"})
    metin = olcum.metin_hali(sonuclar)
    ayar.RAPOR.mkdir(parents=True, exist_ok=True)
    yol = ayar.RAPOR / f"Hız ölçümü {time.strftime('%Y-%m-%d %H.%M')}.txt"
    yol.write_text(metin, encoding="utf-8")
    _olcum.update(durum="bitti", mesaj="Bitti", metin=metin, dosya=str(yol))


@app.post("/api/olcum")
def olcum_baslat(kid: str = Form(...), ilk: int = Form(100), adet: int = Form(50), cpu_adet: int = Form(8)):
    k = _kitap(kid)
    if not k["yol"].lower().endswith(".pdf") or not os.path.exists(k["yol"]):
        raise HTTPException(400, "Ölçüm için PDF kitap seçilmeli")
    if _olcum.get("durum") in ("sirada", "calisiyor"):
        raise HTTPException(409, "Ölçüm zaten sürüyor")
    _olcum.clear()
    _olcum.update(durum="sirada", mesaj="Sırada (önceki iş bitince başlar)", kitap=k["ad"])
    sira.ek_is("olcum", lambda: _olcum_isi(k["yol"], max(1, ilk), max(1, min(adet, 200)), max(0, min(cpu_adet, 50))))
    return {"ok": True}


# ---------------------------------------------------------------- güncelleme
def _guncelle_isi():
    betik = Path(__file__).parents[1] / "kur.sh"
    _guncelleme.update(durum="calisiyor", mesaj="Yeni sürüm indiriliyor…", zaman=time.time())
    with open(ayar.GUNLUK / "guncelleme.log", "w", encoding="utf-8") as g:
        p = subprocess.run(["/bin/bash", str(betik), "--guncelle"], stdout=g, stderr=subprocess.STDOUT)
    if p.returncode != 0:
        son = (ayar.GUNLUK / "guncelleme.log").read_text(encoding="utf-8").strip().splitlines()[-3:]
        _guncelleme.update(durum="hata", mesaj="Güncellenemedi: " + " / ".join(son))
        return
    _guncelleme.update(durum="yeniden", mesaj="Yeniden başlatılıyor…")
    while sira.mesgul():          # işlenen kitap varsa bitmesi beklenir
        _guncelleme["mesaj"] = "Yeniden başlatma, işlenen kitabın bitmesini bekliyor…"
        time.sleep(5)
    time.sleep(1)
    os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "hazirlik.sunucu:app",
                              "--host", "127.0.0.1", "--port", str(ayar.PORT)])


@app.post("/api/guncelle")
def guncelle():
    if _guncelleme.get("durum") in ("calisiyor", "yeniden"):
        raise HTTPException(409, "Güncelleme sürüyor")
    if not (Path(__file__).parents[1] / "kur.sh").exists():
        raise HTTPException(400, "kur.sh yok")
    threading.Thread(target=_guncelle_isi, daemon=True).start()
    return {"ok": True}


@app.exception_handler(HTTPException)
def _hata(_, e):
    return JSONResponse({"hata": e.detail}, status_code=e.status_code)
