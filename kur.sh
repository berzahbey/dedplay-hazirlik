#!/bin/bash
# Dedplay Hazırlık — kurulum (bir kez) ve güncelleme ("Güncelle" düğmesi bunu --guncelle ile çalıştırır).
#
# Kurulum (Terminal'de bir kez):
#   curl -fsSL https://raw.githubusercontent.com/berzahbey/dedplay-hazirlik/main/kur.sh | bash
# ya da Mac'teki kopyadan:
#   bash ~/Dedplay/mac-studyo/hazirlik/kur.sh
#
# Ne yapar: uv + Python 3.11 ortamı, Stüdyo'nun kodu (GitHub, berzahbey/dedplay-studyo), Surya OCR (Apple ekran kartı),
# Tesseract ve Java (epubcheck için; uygulamanın kendi klasöründe, Homebrew gerekmez), yazı tipleri, sözlük,
# ~/Dedplay/Hazırlık/{Gelen,Temiz,Rapor} klasörleri, ~/Applications/Dedplay Hazırlık.app ve Dock simgesi.
# Sistemde hiçbir şeyi değiştirmez (yönetici şifresi istemez). Her şey:
#   ~/Library/Application Support/Dedplay Hazirlik/
# Bu betik macOS'un bash 3.2'siyle çalışır (bash 4 özellikleri kullanılmaz).
set -euo pipefail

GUNCELLE=0
[ "${1:-}" = "--guncelle" ] && GUNCELLE=1
UYG="${HAZIRLIK_UYGULAMA:-$HOME/Library/Application Support/Dedplay Hazirlik}"
KLASOR="${HAZIRLIK_KLASOR:-$HOME/Dedplay/Hazırlık}"
KOD="$UYG/kod"
DEPO_H="berzahbey/dedplay-hazirlik"
DEPO_S="berzahbey/dedplay-studyo"
PORT="${HAZIRLIK_PORT:-8071}"
APP="$HOME/Applications/Dedplay Hazırlık.app"
MAC=0; [ "$(uname -s)" = "Darwin" ] && MAC=1

adim() { printf '\n==> %s\n' "$*"; }
indir() { curl -fL --retry 3 --retry-delay 2 -sS -o "$2" "$1"; }

# Bütün iş bir işlevde: 'curl | bash' ile çalışırken alt komutlar betiğin geri kalanını stdin'den yiyemez
ana() {
if [ "$MAC" = 1 ] && [ "$(uname -m)" != "arm64" ]; then
  echo "Bu uygulama Apple Silicon (M1/M2/M3…) Mac içindir."; exit 1
fi
mkdir -p "$UYG" "$KOD" "$UYG/gunluk"
exec > >(tee -a "$UYG/gunluk/kurulum.log") 2>&1
echo "---- $(date) kur.sh $* ----"

# ------------------------------------------------------------ 1. uv
adim "uv (Python yöneticisi)"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
uv --version

# ------------------------------------------------------------ 2. kod
# Kaynak: GitHub ya da (depo hazır olmadan önce) Mac'teki bir klasör. İlk kurulumda betiğin yanında hazirlik/ varsa o klasör
# kaynak olur ve "Güncelle" de oradan alır; curl ile kurulunca GitHub.
BETIK_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  BETIK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ "$GUNCELLE" = 1 ] && [ -f "$UYG/kaynak" ]; then
  KAYNAK="$(cat "$UYG/kaynak")"
elif [ -n "$BETIK_DIR" ] && [ -f "$BETIK_DIR/hazirlik/__init__.py" ] && [ "$BETIK_DIR" != "$KOD/hazirlik" ]; then
  KAYNAK="$BETIK_DIR"
else
  KAYNAK="github"
fi
if [ "$KAYNAK" != "github" ] && [ ! -f "$KAYNAK/hazirlik/__init__.py" ]; then
  echo "Yerel kaynak bulunamadı ($KAYNAK), GitHub'dan alınacak"; KAYNAK="github"
fi
echo "$KAYNAK" > "$UYG/kaynak"

adim "Dedplay Hazırlık kodu ($KAYNAK)"
rm -rf "$KOD/hazirlik.yeni"; mkdir -p "$KOD/hazirlik.yeni"
if [ "$KAYNAK" = "github" ]; then
  curl -fsSL "https://codeload.github.com/$DEPO_H/tar.gz/refs/heads/main" | tar xz --strip-components=1 -C "$KOD/hazirlik.yeni"
else
  (cd "$KAYNAK" && tar cf - --exclude .git --exclude __pycache__ .) | tar xf - -C "$KOD/hazirlik.yeni"
fi
[ -f "$KOD/hazirlik.yeni/hazirlik/__init__.py" ] || { echo "İndirilen kod eksik"; exit 1; }
rm -rf "$KOD/hazirlik.eski"; [ -d "$KOD/hazirlik" ] && mv "$KOD/hazirlik" "$KOD/hazirlik.eski"
mv "$KOD/hazirlik.yeni" "$KOD/hazirlik"
grep '^SURUM' "$KOD/hazirlik/hazirlik/__init__.py"

adim "Stüdyo kodu (github.com/$DEPO_S)"
rm -rf "$KOD/studyo.yeni"; mkdir -p "$KOD/studyo.yeni"
if [ -n "${HAZIRLIK_STUDYO_KAYNAK:-}" ]; then          # yalnız deneme için: başka bir Stüdyo kodu klasörü
  (cd "$HAZIRLIK_STUDYO_KAYNAK" && tar cf - --exclude .git --exclude __pycache__ .) | tar xf - -C "$KOD/studyo.yeni"
  echo "yerel" > "$KOD/studyo.yeni/.commit"
else
  curl -fsSL "https://codeload.github.com/$DEPO_S/tar.gz/refs/heads/main" | tar xz --strip-components=1 -C "$KOD/studyo.yeni"
  curl -fsS -m 15 -H "Accept: application/vnd.github.sha" "https://api.github.com/repos/$DEPO_S/commits/main" \
    > "$KOD/studyo.yeni/.commit" 2>/dev/null || echo "" > "$KOD/studyo.yeni/.commit"
fi
[ -f "$KOD/studyo.yeni/kutuphane/kaynak.py" ] || { echo "Stüdyo kodu eksik"; exit 1; }
rm -rf "$KOD/studyo.eski"; [ -d "$KOD/studyo" ] && mv "$KOD/studyo" "$KOD/studyo.eski"
mv "$KOD/studyo.yeni" "$KOD/studyo"
grep '^SURUM' "$KOD/studyo/kutuphane/main.py" || true

# ------------------------------------------------------------ 3. Python ortamı
adim "Python 3.11 ortamı ve kütüphaneler (ilk kurulumda birkaç dakika)"
PY="$UYG/.venv/bin/python"
[ -x "$PY" ] || uv venv -q -p 3.11 "$UYG/.venv"
uv pip install -q -p "$PY" -r "$KOD/hazirlik/requirements.txt"
"$PY" -c "import torch, fitz, surya; print('torch', torch.__version__, '| MPS:', torch.backends.mps.is_available())"

# ------------------------------------------------------------ 4. Tesseract + Java (micromamba, conda-forge)
if [ ! -x "$UYG/ortam/bin/tesseract" ] || [ ! -x "$UYG/ortam/bin/java" ]; then
  adim "Tesseract ve Java (uygulamanın kendi klasörüne)"
  if [ "$MAC" = 1 ]; then PLAT="osx-arm64"; else PLAT="linux-64"; fi
  mkdir -p "$UYG/mamba/bin"
  if [ ! -x "$UYG/mamba/bin/micromamba" ]; then
    curl -fsSL "https://micro.mamba.pm/api/micromamba/$PLAT/latest" | tar xj -C "$UYG/mamba" bin/micromamba
  fi
  MAMBA_ROOT_PREFIX="$UYG/mamba" "$UYG/mamba/bin/micromamba" create -y -q -p "$UYG/ortam" -c conda-forge tesseract "openjdk>=17"
fi
"$UYG/ortam/bin/tesseract" --version 2>&1 | head -1

# Stüdyo imajındaki gibi: Türkçe tessdata_best, İngilizce ve osd (yön) standart
mkdir -p "$UYG/tessdata"
[ -s "$UYG/tessdata/tur.traineddata" ] || indir https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/tur.traineddata "$UYG/tessdata/tur.traineddata"
[ -s "$UYG/tessdata/eng.traineddata" ] || indir https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/eng.traineddata "$UYG/tessdata/eng.traineddata"
[ -s "$UYG/tessdata/osd.traineddata" ] || indir https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/osd.traineddata "$UYG/tessdata/osd.traineddata"

# ------------------------------------------------------------ 5. epubcheck, yazı tipleri, sözlük
if [ ! -f "$UYG/epubcheck/epubcheck.jar" ]; then
  adim "epubcheck 5.4.0"
  indir https://github.com/w3c/epubcheck/releases/download/v5.4.0/epubcheck-5.4.0.zip "$UYG/epubcheck.zip"
  rm -rf "$UYG/epubcheck" "$UYG/epubcheck-5.4.0"
  (cd "$UYG" && unzip -q epubcheck.zip && mv epubcheck-5.4.0 epubcheck && rm epubcheck.zip)
fi
mkdir -p "$UYG/fontlar" "$UYG/veri-dosyalari"
[ -s "$UYG/fontlar/Amiri-Regular.ttf" ] || indir https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Regular.ttf "$UYG/fontlar/Amiri-Regular.ttf"
[ -s "$UYG/fontlar/Amiri-Bold.ttf" ] || indir https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Bold.ttf "$UYG/fontlar/Amiri-Bold.ttf"
[ -s "$UYG/veri-dosyalari/tr_kelime.txt" ] || indir https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/tr/tr_50k.txt "$UYG/veri-dosyalari/tr_kelime.txt"

# ------------------------------------------------------------ 6. klasörler ve Surya modelleri
mkdir -p "$KLASOR/Gelen" "$KLASOR/Temiz" "$KLASOR/Rapor" "$UYG/veri" "$UYG/modeller/surya"
if [ ! -f "$UYG/modeller/.surya-tamam" ]; then
  adim "Surya OCR modelleri (bir kez, ~1,5 GB)"
  if (cd "$KOD/hazirlik" && MODEL_CACHE_DIR="$UYG/modeller/surya" TORCH_DEVICE=cpu "$PY" -c "
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
RecognitionPredictor(); DetectionPredictor(); print('Surya modelleri hazır')"); then
    touch "$UYG/modeller/.surya-tamam"
  else
    echo "UYARI: Surya modelleri inmedi; ilk taranmış kitapta yeniden denenir."
  fi
fi

# ------------------------------------------------------------ 7. başlatıcı, .app ve Dock
cat > "$UYG/baslat.sh" <<BASLAT
#!/bin/bash
# Dedplay Hazırlık'ı başlatır (çalışmıyorsa) ve tarayıcıda açar.
UYG="$UYG"
PORT=$PORT
if ! curl -fs -m 2 "http://127.0.0.1:\$PORT/api/durum" >/dev/null 2>&1; then
  mkdir -p "\$UYG/gunluk"
  cd "\$UYG/kod/hazirlik" || exit 1
  nohup "\$UYG/.venv/bin/python" -m uvicorn hazirlik.sunucu:app --host 127.0.0.1 --port \$PORT \\
    >> "\$UYG/gunluk/sunucu.log" 2>&1 < /dev/null &
  disown || true
  for i in \$(seq 1 120); do
    curl -fs -m 1 "http://127.0.0.1:\$PORT/api/durum" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi
[ "\$(uname -s)" = "Darwin" ] && open "http://127.0.0.1:\$PORT/"
exit 0
BASLAT
chmod +x "$UYG/baslat.sh"

if [ "$MAC" = 1 ]; then
  adim "Dedplay Hazırlık.app ve Dock simgesi"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  printf '#!/bin/bash\nexec "%s/baslat.sh"\n' "$UYG" > "$APP/Contents/MacOS/dedplay-hazirlik"
  chmod +x "$APP/Contents/MacOS/dedplay-hazirlik"
  cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>dedplay-hazirlik</string>
  <key>CFBundleIdentifier</key><string>nl.dedplay.hazirlik</string>
  <key>CFBundleName</key><string>Dedplay Hazırlık</string>
  <key>CFBundleDisplayName</key><string>Dedplay Hazırlık</string>
  <key>CFBundleIconFile</key><string>simge</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PLIST
  if [ -f "$KOD/hazirlik/icon.png" ]; then
    SET="$UYG/simge.iconset"; rm -rf "$SET"; mkdir -p "$SET"
    for b in 16 32 128 256 512; do
      sips -z $b $b "$KOD/hazirlik/icon.png" --out "$SET/icon_${b}x${b}.png" >/dev/null
      b2=$((b * 2)); sips -z $b2 $b2 "$KOD/hazirlik/icon.png" --out "$SET/icon_${b}x${b}@2x.png" >/dev/null
    done
    iconutil -c icns "$SET" -o "$APP/Contents/Resources/simge.icns" && rm -rf "$SET"
  fi
  touch "$APP"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true
  URL="file://$("$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$APP")/"
  if ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Dedplay%20Haz"; then
    defaults write com.apple.dock persistent-apps -array-add "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$URL</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"
    killall Dock || true
  fi
fi

adim "Tamam"
if [ "$GUNCELLE" = 0 ]; then
  echo "Dedplay Hazırlık açılıyor: http://127.0.0.1:$PORT/  (sonra Dock'taki simgeyle açılır)"
  "$UYG/baslat.sh" || true
fi
}

ana "$@"
