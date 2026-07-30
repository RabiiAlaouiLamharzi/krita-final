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

find_krita_app() {
  local p found
  for p in \
    "/Applications/krita.app" \
    "/Applications/Krita.app" \
    "$HOME/Applications/krita.app" \
    "$HOME/Applications/Krita.app" \
    "$HOME/Desktop/krita.app" \
    "$HOME/Desktop/Krita.app" \
    "$HOME/Downloads/krita.app" \
    "$HOME/Downloads/Krita.app"
  do
    if [ -d "$p" ]; then
      echo "$p"
      return 0
    fi
  done
  found="$(mdfind 'kMDItemCFBundleIdentifier == "org.krita"' 2>/dev/null \
    | grep -E '\.app$' | head -1 || true)"
  if [ -n "$found" ] && [ -d "$found" ]; then
    echo "$found"
    return 0
  fi
  found="$(mdfind 'kMDItemFSName == "krita.app"c' 2>/dev/null \
    | grep -E '\.app$' | head -1 || true)"
  if [ -n "$found" ] && [ -d "$found" ]; then
    echo "$found"
    return 0
  fi
  return 1
}

echo ""
echo "Opening Krita…"
KRITA_APP=""
if KRITA_APP="$(find_krita_app)"; then
  echo "Found: $KRITA_APP"
  open -a "$KRITA_APP" --args -nosplash
  exit 0
fi

# Launch Services: works if Krita was opened at least once, even outside Applications.
if open -a krita --args -nosplash 2>/dev/null \
  || open -a Krita --args -nosplash 2>/dev/null; then
  exit 0
fi

echo ""
echo "ERROR: Krita.app not found on this Mac."
echo ""
echo "Do this, then run Launch Study again:"
echo "  1. Install Krita from https://krita.org/en/"
echo "  2. Drag Krita into the Applications folder"
echo "  3. Open Krita once from Applications (click Open if macOS asks)"
echo "  4. Quit Krita, then right-click this Launch Study.command"
echo "     → Open With → Terminal"
echo ""
echo "If macOS blocks Launch Study (unknown developer / identity):"
echo "  System Settings → Privacy & Security → Security → Allow / Open Anyway"
echo "  then right-click → Open With → Terminal again."
echo ""
read -r -p "Press Enter to close…"
exit 1
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

Mac:
  - Right-click "Launch Study.command" → Open With → Terminal
    (do not double-click)
  - If macOS says it cannot verify the developer/identity:
      System Settings → Privacy & Security → scroll to Security →
      Allow / Open Anyway for Launch Study, then right-click again →
      Open With → Terminal
  - After it works once, quit Krita if needed and run Launch Study again

Windows:
  - Double-click "Launch Study.bat"
    (SmartScreen: More info → Run anyway)

3) Log in with the credentials your experimenter sent you.

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
