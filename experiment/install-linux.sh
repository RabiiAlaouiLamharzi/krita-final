#!/bin/bash
# Install the study plugin into the current user's Krita profile (Linux).
# Covers native packages, AppImage (~/.local/share/krita), and Flatpak if present.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

copy_tree() {
  local src="$1"
  local dest="$2"
  mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$src/" "$dest/"
  else
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -a "$src/." "$dest/"
    find "$dest" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
  fi
}

install_into() {
  local krita_support="$1"
  local krita_prefs="$2"
  local plugin_dest="$krita_support/pykrita/hide_ui"
  local shortcuts_dest="$krita_support/shortcuts"
  local css_dest="$krita_support/css_styles"

  mkdir -p "$krita_support/pykrita" "$shortcuts_dest" "$css_dest"
  mkdir -p "$ROOT/participant_data" "$ROOT/layout_states"

  copy_tree "$ROOT/plugin/hide_ui" "$plugin_dest"
  printf '%s\n' "$ROOT/participant_data" > "$plugin_dest/data_root.txt"
  cp "$ROOT/plugin/hide_ui.desktop" "$krita_support/pykrita/"
  cp "$ROOT/config/krita5.xmlgui" "$krita_support/"
  cp "$ROOT/config/study_none.shortcuts" "$shortcuts_dest/study_none.shortcuts"
  cp "$ROOT/config/study_large_text.svg" "$css_dest/Study_Large_Text.svg"

  mkdir -p "$plugin_dest/images"
  if [ -d "$ROOT/images" ]; then
    if command -v rsync >/dev/null 2>&1; then
      rsync -a "$ROOT/images/" "$plugin_dest/images/"
    else
      cp -a "$ROOT/images/." "$plugin_dest/images/"
    fi
    echo "Copied images/ → $plugin_dest/images"
  else
    echo "WARNING: $ROOT/images/ not found"
  fi

  mkdir -p "$plugin_dest/media"
  if [ -d "$ROOT/media" ]; then
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude '*.mp4' --exclude '*.mov' --exclude '*.mkv' --exclude '*.webm' \
        "$ROOT/media/" "$plugin_dest/media/"
    else
      cp -a "$ROOT/media/." "$plugin_dest/media/"
      find "$plugin_dest/media" -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.mkv' -o -name '*.webm' \) -delete
    fi
    echo "Copied media/ (videos excluded)"
  fi

  rm -f "$ROOT/layout_states/"*.state 2>/dev/null || true

  if command -v python3 >/dev/null 2>&1; then
    python3 "$ROOT/scripts/patch_kritarc.py" "$krita_prefs"
  else
    echo "ERROR: python3 is required to patch kritarc."
    echo "Install python3, then run this installer again."
    exit 1
  fi

  echo "Installed plugin to:"
  echo "  $plugin_dest"
  echo "Patched:"
  echo "  $krita_prefs"
}

echo "=== Krita Study install (Linux) ==="
echo "Pack root: $ROOT"

NATIVE_SUPPORT="${XDG_DATA_HOME:-$HOME/.local/share}/krita"
NATIVE_PREFS="${XDG_CONFIG_HOME:-$HOME/.config}/kritarc"
install_into "$NATIVE_SUPPORT" "$NATIVE_PREFS"

FLATPAK_SUPPORT="$HOME/.var/app/org.kde.krita/data/krita"
FLATPAK_PREFS="$HOME/.var/app/org.kde.krita/config/kritarc"
if [ -d "$HOME/.var/app/org.kde.krita" ] || command -v flatpak >/dev/null 2>&1; then
  if flatpak info org.kde.krita >/dev/null 2>&1 || [ -d "$HOME/.var/app/org.kde.krita" ]; then
    echo "Also installing into Flatpak Krita profile…"
    install_into "$FLATPAK_SUPPORT" "$FLATPAK_PREFS"
  fi
fi

echo "Install finished."
echo "Launch with: krita --nosplash"
echo "  or: flatpak run org.kde.krita --nosplash"
echo "  or: your Krita AppImage --nosplash"
