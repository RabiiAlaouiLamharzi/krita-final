#!/bin/bash
set -euo pipefail
KRITA_SUPPORT="$HOME/Library/Application Support/krita"
KRITA_PREFS="$HOME/Library/Preferences/kritarc"
osascript -e 'tell application "krita" to quit' >/dev/null 2>&1 || true
killall krita >/dev/null 2>&1 || true
sleep 1
rm -rf "$KRITA_SUPPORT/pykrita/hide_ui"
rm -f "$KRITA_SUPPORT/pykrita/hide_ui.desktop"
rm -f "$KRITA_SUPPORT/krita5.xmlgui"
rm -f "$KRITA_SUPPORT/shortcuts/study_none.shortcuts"
rm -f "$KRITA_SUPPORT/css_styles/Study_Large_Text.svg"
rm -f "$HOME/krita_hide_ui_log.txt"
if [ -f "$KRITA_PREFS" ]; then
  TMP="$(mktemp)"
  tr -d '\r' < "$KRITA_PREFS" | sed '/^State=/d' | sed '/^DockWidget .*\/DockArea=/d' > "$TMP" || true
  if grep -q '^showStatusBar=' "$TMP" 2>/dev/null; then
    sed -i.bak 's/^showStatusBar=.*/showStatusBar=true/' "$TMP"
    rm -f "$TMP.bak"
  else
    printf 'showStatusBar=true\n' >> "$TMP"
  fi
  if grep -q '^\[python\]$' "$TMP" 2>/dev/null; then
    if grep -q '^enable_hide_ui=' "$TMP" 2>/dev/null; then
      sed -i.bak 's/^enable_hide_ui=.*/enable_hide_ui=false/' "$TMP"
      rm -f "$TMP.bak"
    else
      awk 'BEGIN{d=0} /^\[python\]$/{print;print "enable_hide_ui=false";d=1;next} {print}' "$TMP" > "$TMP.out"
      mv "$TMP.out" "$TMP"
    fi
  else
    printf '\n[python]\nenable_hide_ui=false\n' >> "$TMP"
  fi
  if grep -q '^Current Scheme=' "$TMP" 2>/dev/null; then
    sed -i.bak 's/^Current Scheme=.*/Current Scheme=Default/' "$TMP"
    rm -f "$TMP.bak"
  fi
  mv "$TMP" "$KRITA_PREFS"
fi
echo ""
echo "Study mode removed."
echo "Open Krita from Applications to use the normal version."
echo ""
read -r -p "Press Enter to close…"
