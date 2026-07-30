#!/bin/bash
set -euo pipefail

PREFS="${1:?}"
mkdir -p "$(dirname "$PREFS")"
touch "$PREFS"

python_bin=""
for cand in python3 python /usr/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import re' >/dev/null 2>&1; then
      python_bin="$cand"
      break
    fi
  fi
done

if [ -n "$python_bin" ]; then
  ROOT="$(cd "$(dirname "$0")" && pwd)"
  "$python_bin" "$ROOT/patch_kritarc.py" "$PREFS"
  exit 0
fi

TMP="$(mktemp)"
tr -d '\r' < "$PREFS" | sed '/^State=/d' > "$TMP" || true

set_root() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$TMP" 2>/dev/null; then
    sed -i.bak "s|^${key}=.*|${key}=${value}|" "$TMP"
    rm -f "$TMP.bak"
  else
    printf '%s=%s\n' "$key" "$value" >> "$TMP"
  fi
}

ensure_section() {
  local section="$1"
  if ! grep -q "^\[${section}\]$" "$TMP" 2>/dev/null; then
    printf '\n[%s]\n' "$section" >> "$TMP"
  fi
}

set_section() {
  local section="$1" key="$2" value="$3"
  ensure_section "$section"
  awk -v section="$section" -v key="$key" -v value="$value" '
    BEGIN { insec=0; done=0 }
    {
      if ($0 ~ /^\[/) {
        if (insec && !done) {
          print key "=" value
          done=1
        }
        insec = ($0 == "[" section "]")
        print
        next
      }
      if (insec && $0 ~ ("^" key "=")) {
        print key "=" value
        done=1
        next
      }
      print
    }
    END {
      if (insec && !done) print key "=" value
      if (!done && !insec) {
        print ""
        print "[" section "]"
        print key "=" value
      }
    }
  ' "$TMP" > "$TMP.out"
  mv "$TMP.out" "$TMP"
}

set_root "showStatusBar" "false"
set_root "toolbarslider_1" "size"
set_section "MainWindow" "toolOptionsInDocker" "false"
set_section "MainWindow" "newCursorStyle" "2"
set_section "python" "enable_hide_ui" "true"
set_section "SelectedTags" "paintoppreset" "All"
set_section "SvgTextTool" "useCurrentTextProperties" "true"
set_section "SvgTextTool" "cssStylePresetName" ""
set_section "Shortcut Schemes" "Current Scheme" "study_none"

DOCKERS="AnimationCurveDocker AnimationDocker ArrangeDocker ArtisticColorSelector BrushHudDocker ChannelDocker CompositionDocker DigitalMixer FlipbookDocker GamutMask GridDocker HistogramDocker History KisHistogramDocker KisTriangleColorSelector KoColorDocker KoPaletteDocker KoShapeCollectionDocker LogDocker LutDocker OnionSkinsDocker OverviewDocker PaletteDocker PatternDocker PresetHistory RecorderDocker Scripting SmallColorSelector Snapshot SpecificColorSelector StoryboardDocker SvgSymbolCollectionDocker TasksetDocker TextDocumentInspectionDocker TimelineDocker TouchDocker WideGamutColorSelector comics_project_manager_docker lastdocumentsdocker mutatorDocker pykrita_workflow_buttons quick_settings_docker sharedtooldocker TextProperties"
for name in $DOCKERS; do
  set_section "MainWindow" "DockWidget ${name}/DockArea" "256"
done

mv "$TMP" "$PREFS"
echo "Updated $PREFS"
