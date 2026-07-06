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

mkdir -p "$PLUGIN_DEST/media"
if [ -d "$ROOT/media" ]; then
  rsync -a "$ROOT/media/" "$PLUGIN_DEST/media/"
  echo "Copied media/ ($(ls "$ROOT/media" 2>/dev/null | wc -l | tr -d ' ') files)"
else
  echo "WARNING: $ROOT/media/ not found — add session videos there."
fi

mkdir -p "$ROOT/layout_states"
# Drop cached layout blobs so dock positions are rebuilt with the fixed preset strip.
rm -f "$ROOT/layout_states/"*.state 2>/dev/null || true

python3 <<'PY'
import os
import re

prefs = os.path.expanduser("~/Library/Preferences/kritarc")
text = open(prefs).read() if os.path.isfile(prefs) else ""

def set_root(key, value):
    global text
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, text, flags=re.M):
        text = re.sub(pat, line, text, flags=re.M)
    else:
        text = text.rstrip() + "\n" + line + "\n"

def set_mainwindow(key, value):
    global text
    if "[MainWindow]" not in text:
        text += "\n[MainWindow]\n"
    block = re.search(r"\[MainWindow\][^\[]*", text, flags=re.S)
    body = block.group(0) if block else "[MainWindow]\n"
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, body, flags=re.M):
        body = re.sub(pat, line, body, flags=re.M)
    else:
        body = body.rstrip() + "\n" + line + "\n"
    text = text[:block.start()] + body + text[block.end():] if block else text

def set_python(key, value):
    global text
    if "[python]" not in text:
        text += "\n[python]\n"
    block = re.search(r"\[python\][^\[]*", text, flags=re.S)
    body = block.group(0) if block else "[python]\n"
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, body, flags=re.M):
        body = re.sub(pat, line, body, flags=re.M)
    else:
        body = body.rstrip() + "\n" + line + "\n"
    text = text[:block.start()] + body + text[block.end():] if block else text

def set_selected_tags(resource_type, value):
    global text
    if "[SelectedTags]" not in text:
        text += "\n[SelectedTags]\n"
    block = re.search(r"\[SelectedTags\][^\[]*", text, flags=re.S)
    body = block.group(0) if block else "[SelectedTags]\n"
    pat = r"^%s=.*$" % re.escape(resource_type)
    line = "%s=%s" % (resource_type, value)
    if re.search(pat, body, flags=re.M):
        body = re.sub(pat, line, body, flags=re.M)
    else:
        body = body.rstrip() + "\n" + line + "\n"
    text = text[:block.start()] + body + text[block.end():] if block else text

def set_group(section, key, value):
    global text
    if "[%s]" % section not in text:
        text += "\n[%s]\n" % section
    block = re.search(r"\[%s\][^\[]*" % re.escape(section), text, flags=re.S)
    body = block.group(0) if block else "[%s]\n" % section
    pat = r"^%s=.*$" % re.escape(key)
    line = "%s=%s" % (key, value)
    if re.search(pat, body, flags=re.M):
        body = re.sub(pat, line, body, flags=re.M)
    else:
        body = body.rstrip() + "\n" + line + "\n"
    text = text[:block.start()] + body + text[block.end():] if block else text

# Remove saved window layout blob so xmlgui + plugin control the UI.
text = re.sub(r"\nState=[^\n]*", "", text)

set_root("showStatusBar", "false")
set_root("toolbarslider_1", "size")
set_mainwindow("toolOptionsInDocker", "false")
set_mainwindow("newCursorStyle", "2")
set_python("enable_hide_ui", "true")
set_selected_tags("paintoppreset", "All")
# SvgTextTool: keep canvas text properties (plugin sets a large default).
set_group("SvgTextTool", "useCurrentTextProperties", "true")
set_group("SvgTextTool", "cssStylePresetName", "")
set_group("Shortcut Schemes", "Current Scheme", "study_none")

hidden = [
    "AnimationCurveDocker", "AnimationDocker", "ArrangeDocker", "ArtisticColorSelector",
    "BrushHudDocker", "ChannelDocker", "CompositionDocker", "DigitalMixer",
    "FlipbookDocker", "GamutMask", "GridDocker", "HistogramDocker", "History",
    "KisHistogramDocker", "KisTriangleColorSelector", "KoColorDocker", "KoPaletteDocker",
    "KoShapeCollectionDocker", "LogDocker", "LutDocker", "OnionSkinsDocker",
    "OverviewDocker", "PaletteDocker", "PatternDocker", "PresetHistory",
    "RecorderDocker", "Scripting", "SmallColorSelector", "Snapshot",
    "SpecificColorSelector", "StoryboardDocker", "SvgSymbolCollectionDocker",
    "TasksetDocker", "TextDocumentInspectionDocker", "TimelineDocker", "TouchDocker",
    "WideGamutColorSelector", "comics_project_manager_docker", "lastdocumentsdocker",
    "mutatorDocker", "pykrita_workflow_buttons", "quick_settings_docker", "sharedtooldocker",
    "TextProperties",
]
if "[MainWindow]" not in text:
    text += "\n[MainWindow]\n"
for name in hidden:
    key = "DockWidget %s/DockArea" % name
    set_mainwindow(key, "256")

open(prefs, "w").write(text)
print("Updated", prefs)
PY

echo "Installed experiment plugin to:"
echo "  $PLUGIN_DEST"
echo "Launch with: open -a /Applications/krita.app --args -nosplash"
