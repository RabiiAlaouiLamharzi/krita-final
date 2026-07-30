#!/bin/bash
# Install experiment customizations into the current user's Krita profile (macOS).
# Run this after copying the experiment folder onto a participant machine,
# or bake its steps into your downloadable Krita .dmg / installer.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
KRITA_SUPPORT="$HOME/Library/Application Support/krita"
KRITA_PREFS="$HOME/Library/Preferences/kritarc"
PLUGIN_DEST="$KRITA_SUPPORT/pykrita/hide_ui"
SHORTCUTS_DEST="$KRITA_SUPPORT/shortcuts"

mkdir -p "$KRITA_SUPPORT/pykrita"
mkdir -p "$SHORTCUTS_DEST"

mkdir -p "$ROOT/participant_data"
mkdir -p "$ROOT/layout_states"

# Keep shipped layout blobs; only drop stale version files if we bump STATE_VERSION later.
rsync -a --delete --exclude '__pycache__' "$ROOT/plugin/hide_ui/" "$PLUGIN_DEST/"
echo "$ROOT/participant_data" > "$PLUGIN_DEST/data_root.txt"
cp "$ROOT/plugin/hide_ui.desktop" "$KRITA_SUPPORT/pykrita/"
cp "$ROOT/config/krita5.xmlgui" "$KRITA_SUPPORT/"
cp "$ROOT/config/study_none.shortcuts" "$SHORTCUTS_DEST/study_none.shortcuts"

CSS_STYLES_DEST="$KRITA_SUPPORT/css_styles"
mkdir -p "$CSS_STYLES_DEST"
cp "$ROOT/config/study_large_text.svg" "$CSS_STYLES_DEST/Study_Large_Text.svg"

mkdir -p "$PLUGIN_DEST/images"
if [ -d "$ROOT/images" ]; then
  rsync -a "$ROOT/images/" "$PLUGIN_DEST/images/"
  echo "Copied images/ (including images-steps)"
else
  echo "WARNING: $ROOT/images/ not found — add tutorial reference PNGs there."
fi

mkdir -p "$PLUGIN_DEST/media"
if [ -d "$ROOT/media" ]; then
  rsync -a --exclude '*.mp4' --exclude '*.mov' --exclude '*.mkv' --exclude '*.webm' \
    "$ROOT/media/" "$PLUGIN_DEST/media/"
  echo "Copied media/ (videos excluded)"
else
  echo "WARNING: $ROOT/media/ not found — intro images may be missing."
fi

mkdir -p "$ROOT/layout_states"
# Drop cached layout blobs so dock positions are rebuilt with the fixed preset strip.
rm -f "$ROOT/layout_states/"*.state 2>/dev/null || true

bash "$ROOT/scripts/patch_kritarc.sh" "$KRITA_PREFS"

if [ ! -d "$PLUGIN_DEST" ] || [ ! -f "$KRITA_SUPPORT/pykrita/hide_ui.desktop" ]; then
  echo "ERROR: study plugin files were not installed." >&2
  exit 1
fi
if ! grep -q '^enable_hide_ui=true' "$KRITA_PREFS" 2>/dev/null \
  && ! grep -q 'enable_hide_ui=true' "$KRITA_PREFS" 2>/dev/null; then
  echo "ERROR: could not enable the study plugin in kritarc." >&2
  exit 1
fi

echo "Installed experiment plugin to:"
echo "  $PLUGIN_DEST"
echo "Study plugin enabled in kritarc."
if [ -n "${KRITA_APP:-}" ]; then
  echo "Launch with: open \"$KRITA_APP\" --args -nosplash"
else
  echo "Launch with: open -a /Applications/krita.app --args -nosplash"
fi
