$ErrorActionPreference = "Stop"
$KritaSupport = Join-Path $env:APPDATA "krita"
$Prefs = Join-Path $KritaSupport "kritarc"
Get-Process -Name "krita" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$PluginDest = Join-Path $KritaSupport "pykrita\hide_ui"
if (Test-Path $PluginDest) { Remove-Item -Recurse -Force $PluginDest }
$Desktop = Join-Path $KritaSupport "pykrita\hide_ui.desktop"
if (Test-Path $Desktop) { Remove-Item -Force $Desktop }
$XmlGui = Join-Path $KritaSupport "krita5.xmlgui"
if (Test-Path $XmlGui) { Remove-Item -Force $XmlGui }
$Shortcuts = Join-Path $KritaSupport "shortcuts\study_none.shortcuts"
if (Test-Path $Shortcuts) { Remove-Item -Force $Shortcuts }
$Css = Join-Path $KritaSupport "css_styles\Study_Large_Text.svg"
if (Test-Path $Css) { Remove-Item -Force $Css }
$Log = Join-Path $env:USERPROFILE "krita_hide_ui_log.txt"
if (Test-Path $Log) { Remove-Item -Force $Log }
if (Test-Path $Prefs) {
    $py = @"
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
"@
    $tmp = Join-Path $env:TEMP "krita_unpatch_kritarc.py"
    Set-Content -Path $tmp -Value $py -Encoding UTF8
    python $tmp $Prefs
    Remove-Item -Force $tmp -ErrorAction SilentlyContinue
}
Write-Host ""
Write-Host "Study mode removed."
Write-Host "Open Krita again to use the normal version."
Write-Host ""
