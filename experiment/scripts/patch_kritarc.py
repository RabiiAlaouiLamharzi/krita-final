#!/usr/bin/env python3
"""Patch kritarc for the UI learning study (macOS or Windows)."""

from __future__ import print_function

import argparse
import os
import re
import sys


HIDDEN_DOCKERS = [
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


def patch(prefs_path):
    text = open(prefs_path).read() if os.path.isfile(prefs_path) else ""

    def set_root(key, value):
        nonlocal text
        pat = r"^%s=.*$" % re.escape(key)
        line = "%s=%s" % (key, value)
        if re.search(pat, text, flags=re.M):
            text = re.sub(pat, line, text, flags=re.M)
        else:
            text = text.rstrip() + "\n" + line + "\n"

    def set_section(section, key, value):
        nonlocal text
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

    text = re.sub(r"\nState=[^\n]*", "", text)

    set_root("showStatusBar", "false")
    set_root("toolbarslider_1", "size")
    set_section("MainWindow", "toolOptionsInDocker", "false")
    set_section("MainWindow", "newCursorStyle", "2")
    set_section("python", "enable_hide_ui", "true")
    set_section("SelectedTags", "paintoppreset", "All")
    set_section("SvgTextTool", "useCurrentTextProperties", "true")
    set_section("SvgTextTool", "cssStylePresetName", "")
    set_section("Shortcut Schemes", "Current Scheme", "study_none")

    if "[MainWindow]" not in text:
        text += "\n[MainWindow]\n"
    for name in HIDDEN_DOCKERS:
        set_section("MainWindow", "DockWidget %s/DockArea" % name, "256")

    parent = os.path.dirname(prefs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(prefs_path, "w") as f:
        f.write(text)
    print("Updated", prefs_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "prefs",
        nargs="?",
        default=os.path.expanduser("~/Library/Preferences/kritarc"),
        help="Path to kritarc",
    )
    args = parser.parse_args()
    patch(args.prefs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
