#!/bin/bash
# Build a participant-ready macOS zip: Krita.app + study pack + Launch Study.
# Usage:
#   ./build-mac-bundle.sh [/path/to/krita.app]
# Default Krita.app: /Applications/krita.app
# Output: experiment/dist/out/KritaStudy-macOS-<version>.zip

set -euo pipefail

DIST_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT="$(cd "$DIST_DIR/.." && pwd)"
REPO="$(cd "$EXPERIMENT/.." && pwd)"
OUT_DIR="${OUT_DIR:-$DIST_DIR/out}"
KRITA_VERSION="${KRITA_VERSION:-5.3.2}"
SRC_APP="${1:-/Applications/krita.app}"

if [ ! -d "$SRC_APP/Contents/MacOS" ]; then
  echo "ERROR: Krita.app not found at: $SRC_APP" >&2
  echo "Install Krita $KRITA_VERSION, or pass the path to krita.app" >&2
  exit 1
fi

DETECTED="$(defaults read "$SRC_APP/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || true)"
if [ -n "$DETECTED" ]; then
  KRITA_VERSION="$DETECTED"
fi

STAGE="$OUT_DIR/KritaStudy-macOS"
ZIP_NAME="KritaStudy-macOS-${KRITA_VERSION}.zip"

echo "Building $ZIP_NAME from $SRC_APP"

rm -rf "$STAGE"
mkdir -p "$STAGE"

echo "Copying Krita.app (this can take a few minutes)…"
ditto "$SRC_APP" "$STAGE/Krita.app"
# Upstream notarized signature breaks after redistribution (Gatekeeper:
# "damaged"). Ad-hoc resign at build time; Launch Study also re-signs on first run.
if command -v codesign >/dev/null 2>&1; then
  echo "Ad-hoc signing Krita.app for redistribution…"
  codesign --force --deep --sign - "$STAGE/Krita.app" || true
fi
xattr -cr "$STAGE/Krita.app" 2>/dev/null || true

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

# Ensure layout_states / participant_data dirs exist empty for install
mkdir -p "$STAGE/study-pack/participant_data" "$STAGE/study-pack/layout_states"

cat > "$STAGE/Launch Study.command" <<'EOF'
#!/bin/bash
set -euo pipefail
cd "$(cd "$(dirname "$0")" && pwd)"
export KRITA_APP="$(pwd)/Krita.app"

# Downloaded / repackaged Krita.app often fails Gatekeeper with a false
# "Krita is damaged" dialog: quarantine + the original developer signature
# no longer verifies after redistribution. Fix: strip quarantine, then
# replace the signature with a local ad-hoc one, then launch.
echo "Preparing Krita for this Mac…"
echo "  (clearing download quarantine)"
xattr -cr "$KRITA_APP" 2>/dev/null || true
xattr -cr "$(pwd)" 2>/dev/null || true

if command -v codesign >/dev/null 2>&1; then
  echo "  (re-signing app for Gatekeeper — may take a minute)"
  codesign --force --deep --sign - "$KRITA_APP" 2>/dev/null \
    || codesign --force --sign - "$KRITA_APP" 2>/dev/null \
    || echo "  warning: codesign failed; trying to launch anyway"
  xattr -cr "$KRITA_APP" 2>/dev/null || true
fi

echo "Installing study plugin…"
bash "$(pwd)/study-pack/install-mac.sh"
echo ""
echo "Starting Krita Study…"
# Launch the binary directly to avoid Finder re-checking a stale quarantine state.
KRITA_BIN="$KRITA_APP/Contents/MacOS/krita"
if [ -x "$KRITA_BIN" ]; then
  exec "$KRITA_BIN" -nosplash
else
  open "$KRITA_APP" --args -nosplash
fi
EOF
chmod +x "$STAGE/Launch Study.command"

cat > "$STAGE/README-PARTICIPANT.txt" <<EOF
Krita UI Learning Study — macOS
Krita version: ${KRITA_VERSION}

HOW TO START
1. Keep this whole folder together (do not open Krita.app alone).
2. Double-click "Launch Study.command".
3. If macOS blocks the .command: Right-click → Open → Open.
4. Wait while it prepares/re-signs Krita (first launch only), then the study opens.
5. Enter Participant ID, Condition, Session, and password from your experimenter.

IF YOU STILL SEE "damaged"
Open Terminal and run (drag the KritaStudy-macOS folder after the space):
  xattr -cr 
  codesign --force --deep --sign - /path/to/KritaStudy-macOS/Krita.app
Then double-click Launch Study.command again.

NOTES
- First launch installs the study plugin into your Krita profile.
- This is an unsigned research build (not from the Mac App Store).
- No tutorial videos; right panel uses text and images.

Source: https://github.com/RabiiAlaouiLamharzi/krita-final
EOF

echo "Zipping…"
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/$ZIP_NAME"
(
  cd "$OUT_DIR"
  ditto -c -k --sequesterRsrc --keepParent "KritaStudy-macOS" "$ZIP_NAME"
)

echo "Done:"
echo "  $OUT_DIR/$ZIP_NAME"
ls -lh "$OUT_DIR/$ZIP_NAME"
# Free space: drop unpacked stage after zip succeeds
rm -rf "$STAGE"
