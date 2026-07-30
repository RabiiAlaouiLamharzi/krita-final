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
  python3 - "$KRITA_PREFS" <<'PY'
import os, re, sys
prefs = sys.argv[1]
text = open(prefs).read() if os.path.isfile(prefs) else ""
text = re.sub(r"\nState=[^\n]*", "", text)
text = re.sub(r"^DockWidget [^\n]*/DockArea=[^\n]*\n?", "", text, flags=re.M)

def set_root(key, value):
    global text
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, text, flags=re.M):
        text = re.sub(pat, line, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"

def set_section(section, key, value):
    global text
    header = "[%s]" % section
    if header not in text:
        text += "\n%s\n" % header
    block = re.search(r"\[%s\][^\[]*" % re.escape(section), text, flags=re.S)
    body = block.group(0) if block else header + "\n"
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, body, flags=re.M):
        body = re.sub(pat, line, body, flags=re.M)
    else:
        body = body.rstrip() + "\n" + line + "\n"
    if block:
        text = text[:block.start()] + body + text[block.end():]
    else:
        text = text + body

set_root("showStatusBar", "true")
set_section("python", "enable_hide_ui", "false")
set_section("Shortcut Schemes", "Current Scheme", "Default")
open(prefs, "w").write(text)
PY
fi
echo ""
echo "Study mode removed."
echo "Open Krita from Applications to use the normal version."
echo ""
read -r -p "Press Enter to close…"
