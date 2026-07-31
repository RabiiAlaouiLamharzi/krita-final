#!/bin/bash
# Build a participant-ready Windows zip: portable Krita + study pack + launcher.
# Usage:
#   ./build-windows-bundle.sh [/path/to/extracted-krita-portable]
# If no path is given, downloads Krita portable zip for KRITA_VERSION.
# Output: experiment/dist/out/KritaStudy-Windows-<version>.zip
#
# Run this on any machine with curl/unzip (macOS or Linux). The resulting zip
# is for Windows participants.

set -euo pipefail

DIST_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT="$(cd "$DIST_DIR/.." && pwd)"
OUT_DIR="${OUT_DIR:-$DIST_DIR/out}"
KRITA_VERSION="${KRITA_VERSION:-5.3.2}"
CACHE="${CACHE_DIR:-$OUT_DIR/cache}"
STAGE="$OUT_DIR/KritaStudy-Windows"
ZIP_NAME="KritaStudy-Windows-${KRITA_VERSION}.zip"

mkdir -p "$CACHE" "$OUT_DIR"

resolve_portable() {
  if [ -n "${1:-}" ]; then
    echo "$1"
    return
  fi
  local url="https://download.kde.org/stable/krita/${KRITA_VERSION}/krita-x64-${KRITA_VERSION}.zip"
  local zip="$CACHE/krita-x64-${KRITA_VERSION}.zip"
  local extract="$CACHE/krita-x64-${KRITA_VERSION}"
  if [ ! -f "$zip" ]; then
    echo "Downloading $url …" >&2
    curl -L --fail -o "$zip" "$url"
  else
    echo "Using cached $zip" >&2
  fi
  rm -rf "$extract"
  mkdir -p "$extract"
  echo "Extracting portable Krita…" >&2
  unzip -q "$zip" -d "$extract"
  # Find folder that contains bin/krita.exe
  local found
  found="$(find "$extract" -type f -name 'krita.exe' | head -1 || true)"
  if [ -z "$found" ]; then
    echo "ERROR: krita.exe not found after extract" >&2
    exit 1
  fi
  dirname "$(dirname "$found")"
}

PORTABLE="$(resolve_portable "${1:-}")"
if [ ! -f "$PORTABLE/bin/krita.exe" ]; then
  echo "ERROR: portable Krita root invalid (no bin/krita.exe): $PORTABLE" >&2
  exit 1
fi

echo "Building $ZIP_NAME from $PORTABLE"
rm -rf "$STAGE"
mkdir -p "$STAGE/krita"

echo "Copying portable Krita…"
rsync -a "$PORTABLE/" "$STAGE/krita/"

echo "Copying study pack…"
mkdir -p "$STAGE/study-pack"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'participant_data/' \
  --exclude 'analysis/' \
  --exclude 'bin/' \
  --exclude 'dist/out/' \
  --exclude '*.mp4' \
  --exclude '*.mov' \
  --exclude '*.mkv' \
  --exclude '*.webm' \
  --exclude '.DS_Store' \
  "$EXPERIMENT/" "$STAGE/study-pack/"

mkdir -p "$STAGE/study-pack/participant_data" "$STAGE/study-pack/layout_states"

cat > "$STAGE/Launch Study.bat" <<'EOF'
@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Installing study plugin...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0study-pack\install-windows.ps1"
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)
echo.
echo Starting Krita Study...
set "KRITA_EXE="
if exist "%~dp0krita\bin\krita.exe" set "KRITA_EXE=%~dp0krita\bin\krita.exe"
if not defined KRITA_EXE if exist "%~dp0krita\krita.exe" set "KRITA_EXE=%~dp0krita\krita.exe"
if not defined KRITA_EXE (
  echo Could not find krita.exe
  pause
  exit /b 1
)
start "" "%KRITA_EXE%" --nosplash
endlocal
EOF
perl -pi -e 's/\n/\r\n/' "$STAGE/Launch Study.bat"

cat > "$STAGE/README-PARTICIPANT.txt" <<EOF
Krita UI Learning Study — Windows
Krita version: ${KRITA_VERSION}

HOW TO START
1. Keep this whole folder together.
2. Double-click "Launch Study.bat".
3. If Windows SmartScreen appears: More info → Run anyway.
4. Enter the Participant ID, Condition, Session, and password
   your experimenter sent you.

NOTES
- First launch installs the study plugin into your Krita profile (%APPDATA%\\krita).
- No tutorial videos are included; the right panel uses text and images.
- Need help? Contact your experimenter / research team.

Source: https://github.com/RabiiAlaouiLamharzi/krita-final
EOF

echo "Zipping…"
rm -f "$OUT_DIR/$ZIP_NAME"
(
  cd "$OUT_DIR"
  # Prefer zip if available
  if command -v zip >/dev/null 2>&1; then
    rm -f "$ZIP_NAME"
    zip -r -q "$ZIP_NAME" "KritaStudy-Windows"
  else
    ditto -c -k --keepParent "KritaStudy-Windows" "$ZIP_NAME"
  fi
)

echo "Done:"
echo "  $OUT_DIR/$ZIP_NAME"
ls -lh "$OUT_DIR/$ZIP_NAME"
rm -rf "$STAGE"
