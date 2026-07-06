#!/bin/bash
# Copy QtMultimedia + PyQt5 bindings into an existing krita.app bundle.
# Use after building Krita with KRITA_ENABLE_QTMULTIMEDIA=ON, or to patch
# from a krita-deps _install prefix.
#
# Usage:
#   ./patch-krita-multimedia.sh /path/to/krita.app /path/to/_install
#
# The _install prefix must contain:
#   lib/QtMultimedia.framework
#   lib/QtMultimediaWidgets.framework
#   lib/Python.framework/.../site-packages/PyQt5/QtMultimedia*.so

set -euo pipefail

KRITA_APP="${1:?Usage: $0 /path/to/krita.app /path/to/_install}"
INSTALL="${2:?Usage: $0 /path/to/krita.app /path/to/_install}"

FRAMEWORKS="$KRITA_APP/Contents/Frameworks"
PY_SITE="$(find "$INSTALL/lib/Python.framework/Versions" -path '*/site-packages' -type d 2>/dev/null | sort -V | tail -1)"
PY_DEST="$(find "$FRAMEWORKS/Python.framework/Versions" -path '*/site-packages/PyQt5' -type d 2>/dev/null | head -1)"

if [ ! -d "$FRAMEWORKS" ]; then
  echo "Not a macOS app bundle: $KRITA_APP" >&2
  exit 1
fi

for fw in QtMultimedia QtMultimediaWidgets; do
  src="$INSTALL/lib/${fw}.framework"
  if [ ! -d "$src" ]; then
    echo "Missing $src — rebuild Qt/PyQt with Multimedia enabled." >&2
    exit 1
  fi
  echo "Copying $fw.framework"
  rsync -a "$src" "$FRAMEWORKS/"
done

if [ -z "$PY_SITE" ] || [ -z "$PY_DEST" ]; then
  echo "Could not locate PyQt5 site-packages in install prefix or krita.app" >&2
  exit 1
fi

for mod in QtMultimedia QtMultimediaWidgets; do
  shopt -s nullglob
  files=("$PY_SITE/PyQt5/${mod}"*.so "$PY_SITE/PyQt5/${mod}.pyi")
  shopt -u nullglob
  if [ ${#files[@]} -eq 0 ]; then
    echo "Missing PyQt5 module $mod in $PY_SITE/PyQt5" >&2
    exit 1
  fi
  for f in "${files[@]}"; do
    echo "Copying $(basename "$f")"
    cp -f "$f" "$PY_DEST/"
  done
done

PY_BIN="$(find "$FRAMEWORKS/Python.framework/Versions" -name 'python3.*' -path '*/bin/*' 2>/dev/null | head -1)"
if [ -n "$PY_BIN" ]; then
  echo "Testing import…"
  "$PY_BIN" -c "from PyQt5.QtMultimedia import QMediaPlayer; from PyQt5.QtMultimediaWidgets import QVideoWidget; print('QtMultimedia OK')"
fi

echo "Done. Re-sign the app if you code-sign for distribution."
