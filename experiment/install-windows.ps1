# Install study plugin into the current user's Krita profile (Windows).
# Run from the study-pack folder (or experiment/) after unzipping the Windows bundle.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$KritaSupport = Join-Path $env:APPDATA "krita"
$Prefs = Join-Path $KritaSupport "kritarc"
$PluginDest = Join-Path $KritaSupport "pykrita\hide_ui"
$ShortcutsDest = Join-Path $KritaSupport "shortcuts"
$CssDest = Join-Path $KritaSupport "css_styles"

New-Item -ItemType Directory -Force -Path (Join-Path $KritaSupport "pykrita") | Out-Null
New-Item -ItemType Directory -Force -Path $ShortcutsDest | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "participant_data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "layout_states") | Out-Null

if (Test-Path $PluginDest) {
    Remove-Item -Recurse -Force $PluginDest
}
New-Item -ItemType Directory -Force -Path $PluginDest | Out-Null

$SrcPlugin = Join-Path $Root "plugin\hide_ui"
Copy-Item -Path (Join-Path $SrcPlugin "*") -Destination $PluginDest -Recurse -Force
Get-ChildItem -Path $PluginDest -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Set-Content -Path (Join-Path $PluginDest "data_root.txt") -Value (Join-Path $Root "participant_data")
Copy-Item (Join-Path $Root "plugin\hide_ui.desktop") (Join-Path $KritaSupport "pykrita\") -Force
Copy-Item (Join-Path $Root "config\krita5.xmlgui") $KritaSupport -Force
Copy-Item (Join-Path $Root "config\study_none.shortcuts") (Join-Path $ShortcutsDest "study_none.shortcuts") -Force

New-Item -ItemType Directory -Force -Path $CssDest | Out-Null
Copy-Item (Join-Path $Root "config\study_large_text.svg") (Join-Path $CssDest "Study_Large_Text.svg") -Force

$ImgDest = Join-Path $PluginDest "images"
New-Item -ItemType Directory -Force -Path $ImgDest | Out-Null
$ImgSrc = Join-Path $Root "images"
if (Test-Path $ImgSrc) {
    Copy-Item -Path (Join-Path $ImgSrc "*") -Destination $ImgDest -Recurse -Force
    Write-Host "Copied images/"
}

$MediaDest = Join-Path $PluginDest "media"
New-Item -ItemType Directory -Force -Path $MediaDest | Out-Null
$MediaSrc = Join-Path $Root "media"
if (Test-Path $MediaSrc) {
    Copy-Item -Path (Join-Path $MediaSrc "*") -Destination $MediaDest -Recurse -Force
    Get-ChildItem -Path $MediaDest -Recurse -Include *.mp4,*.mov,*.mkv,*.webm |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Copied media/ (videos excluded)"
}

Remove-Item (Join-Path $Root "layout_states\*.state") -Force -ErrorAction SilentlyContinue

$Patch = Join-Path $Root "scripts\patch_kritarc.ps1"
& powershell -NoProfile -ExecutionPolicy Bypass -File $Patch -Prefs $Prefs

if (-not (Test-Path $PluginDest) -or -not (Test-Path (Join-Path $KritaSupport "pykrita\hide_ui.desktop"))) {
    throw "Study plugin files were not installed."
}
$prefsText = Get-Content -Raw -Path $Prefs -ErrorAction SilentlyContinue
if ($prefsText -notmatch "enable_hide_ui=true") {
    throw "Could not enable the study plugin in kritarc."
}

Write-Host "Installed experiment plugin to:"
Write-Host "  $PluginDest"
Write-Host "Study plugin enabled in kritarc."
Write-Host "Launch with the bundled Launch Study.bat (or krita.exe --nosplash)"
