#!/bin/zsh
# build.sh — package SaveThisVideo as an unsigned macOS .app
#
# Unsigned build: recipients right-click → Open the first time to bypass Gatekeeper.
# For a fully signed + notarized build (seamless double-click), you need an Apple
# Developer ID certificate and notarytool credentials — see build_signed.sh.

# ─────────────────────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")"

APP_NAME="SaveThisVideo"
APP_BUNDLE="dist/${APP_NAME}.app"

if [[ ! -d .venv ]]; then
  echo "Run ./setup.sh first."
  exit 1
fi

echo "→ Installing build dependencies..."
.venv/bin/pip install --quiet --upgrade pyinstaller static-ffmpeg Pillow

echo "→ Generating app icon..."
.venv/bin/python make_icon.py

echo "→ Fetching static ffmpeg binary..."
FFMPEG_BIN=$(.venv/bin/python3 -c "
import static_ffmpeg.run as r
ff, _ = r.get_or_fetch_platform_executables_else_raise()
print(ff)
" | tail -1)
echo "  $FFMPEG_BIN"

echo "→ Building app bundle..."
.venv/bin/pyinstaller \
    --noconfirm \
    --windowed \
    --onedir \
    --name "${APP_NAME}" \
    --collect-all customtkinter \
    --collect-all yt_dlp \
    --collect-all curl_cffi \
    --add-binary="${FFMPEG_BIN}:bin" \
    --icon=icon.icns \
    app.py

# ── Distribution zip ──────────────────────────────────────────────────────────
echo "→ Creating distribution zip..."
DIST_ZIP="dist/${APP_NAME}.zip"
ditto -c -k --keepParent "${APP_BUNDLE}" "${DIST_ZIP}"

echo ""
echo "✓ Done: ${DIST_ZIP}"
echo ""
echo "Recipients: right-click → Open the first time to bypass Gatekeeper."
echo "(Unsigned build — no Developer ID required.)"
