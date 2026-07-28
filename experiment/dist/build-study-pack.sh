#!/bin/bash
# Build a small study pack (no Krita.app): participants install Krita from krita.org.
# Output: KritaStudy-pack.zip (macOS + Windows launchers)

set -euo pipefail

DIST_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT="$(cd "$DIST_DIR/.." && pwd)"
OUT_DIR="${OUT_DIR:-$DIST_DIR/out}"
STAGE="$OUT_DIR/KritaStudy-pack"
ZIP_NAME="KritaStudy-pack.zip"

echo "Building $ZIP_NAME (plugin only, no bundled Krita)"
rm -rf "$STAGE"
mkdir -p "$STAGE/study-pack" "$OUT_DIR"

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

cat > "$STAGE/Launch Study.command" <<'EOF'
#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
xattr -cr "$(pwd)" 2>/dev/null || true

echo "Installing study plugin into your Krita profile…"
bash "$(pwd)/study-pack/install-mac.sh"

echo ""
echo "Opening official Krita…"
if [ -d "/Applications/krita.app" ]; then
  open -a "/Applications/krita.app" --args -nosplash
elif [ -d "$HOME/Applications/krita.app" ]; then
  open -a "$HOME/Applications/krita.app" --args -nosplash
else
  echo "ERROR: Krita.app not found."
  echo "Install Krita 5.3.2 from https://krita.org/en/download/ then run this again."
  read -r -p "Press Enter to close…"
  exit 1
fi
EOF
chmod +x "$STAGE/Launch Study.command"

cat > "$STAGE/Launch Study.bat" <<'EOF'
@echo off
setlocal
cd /d "%~dp0"
echo Installing study plugin into your Krita profile...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0study-pack\install-windows.ps1"
if errorlevel 1 (
  echo Install failed.
  pause
  exit /b 1
)
echo.
echo Opening Krita...
where krita >nul 2>&1
if %errorlevel%==0 (
  start "" krita -nosplash
  goto :done
)
if exist "%ProgramFiles%\Krita (x64)\bin\krita.exe" (
  start "" "%ProgramFiles%\Krita (x64)\bin\krita.exe" -nosplash
  goto :done
)
if exist "%ProgramFiles%\Krita\bin\krita.exe" (
  start "" "%ProgramFiles%\Krita\bin\krita.exe" -nosplash
  goto :done
)
echo ERROR: Could not find krita.exe.
echo Install Krita 5.3.2 from https://krita.org/en/download/ then run this again.
pause
exit /b 1
:done
endlocal
EOF

cat > "$STAGE/README-PARTICIPANT.txt" <<'EOF'
Krita UI Learning Study — setup pack

1) Install Krita 5.3.2 from https://krita.org/en/download/
2) Unzip this folder and keep it together.
3) Mac: Right-click "Launch Study.command" → Open → Open
   Windows: double-click "Launch Study.bat" (SmartScreen: More info → Run anyway)
4) Log in with the credentials your experimenter sent you.

This zip does NOT include Krita itself — only the study plugin installer.
EOF

rm -f "$OUT_DIR/$ZIP_NAME"
(
  cd "$OUT_DIR"
  if command -v zip >/dev/null 2>&1; then
    zip -r -q "$ZIP_NAME" "KritaStudy-pack"
  else
    ditto -c -k --keepParent "KritaStudy-pack" "$ZIP_NAME"
  fi
)
rm -rf "$STAGE"
echo "Done: $OUT_DIR/$ZIP_NAME"
ls -lh "$OUT_DIR/$ZIP_NAME"
