# Install study plugin into the current user's Krita profile (Windows).
# Fixes the known Windows failure modes:
# - patches the REAL kritarc (%LOCALAPPDATA%\kritarc), not Roaming\krita\kritarc
# - also patches Microsoft Store kritarc paths when present
# - writes data_root.txt as UTF-8 (no UTF-16 BOM from Set-Content)
# - never calls python / Microsoft Store python stub
# - verifies plugin files + enable_hide_ui before reporting success

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Get-KritaResourceRoot {
    # Default resource folder (plugins, shortcuts, brushes, etc.)
    $roaming = Join-Path $env:APPDATA "krita"
    # If kritarc already points ResourceDirectory elsewhere, honor it.
    foreach ($rc in @(
            (Join-Path $env:LOCALAPPDATA "kritarc"),
            (Join-Path $env:APPDATA "krita\kritarc")
        )) {
        if (Test-Path $rc) {
            $raw = Get-Content -Raw -Path $rc -ErrorAction SilentlyContinue
            if ($raw -match "(?m)^ResourceDirectory=(.+)$") {
                $dir = $Matches[1].Trim().Replace("/", "\")
                if ($dir -and (Test-Path $dir)) { return $dir }
            }
        }
    }
    return $roaming
}

function Get-KritaRcCandidates {
    $list = New-Object System.Collections.Generic.List[string]
    $primary = Join-Path $env:LOCALAPPDATA "kritarc"
    $list.Add($primary) | Out-Null

    # Microsoft Store Krita sandboxed config
    $pkgRoot = Join-Path $env:LOCALAPPDATA "Packages"
    if (Test-Path $pkgRoot) {
        Get-ChildItem -Path $pkgRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "49800Krita*" -or $_.Name -like "*Krita*" } |
            ForEach-Object {
                $storeRc = Join-Path $_.FullName "LocalCache\Local\kritarc"
                if (-not $list.Contains($storeRc)) { $list.Add($storeRc) | Out-Null }
            }
    }

    # Legacy / wrong location some tools used — patch too so nothing fights us
    $legacy = Join-Path $env:APPDATA "krita\kritarc"
    if (-not $list.Contains($legacy)) { $list.Add($legacy) | Out-Null }

    return $list
}

function Test-StudyEnabled([string]$PrefsPath) {
    if (-not (Test-Path $PrefsPath)) { return $false }
    $raw = Get-Content -Raw -Path $PrefsPath -ErrorAction SilentlyContinue
    return ($raw -match "(?m)^enable_hide_ui=true\s*$") -or ($raw -match "(?ms)\[python\].*?enable_hide_ui=true")
}

function Find-KritaExe {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Krita (x64)\bin\krita.exe"),
        (Join-Path $env:ProgramFiles "Krita\bin\krita.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Krita (x64)\bin\krita.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Krita\bin\krita.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Krita\bin\krita.exe")
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $cmd = Get-Command krita.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }
    return $null
}

Write-Host "=== Krita Study install (Windows) ==="
Write-Host "Pack root: $Root"

# Stop running Krita so plugin + kritarc reload on next start
$running = @(Get-Process -Name "krita","krita.com" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    Write-Host "Closing running Krita so the study plugin can load..."
    $running | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$KritaSupport = Get-KritaResourceRoot
$PluginDest = Join-Path $KritaSupport "pykrita\hide_ui"
$ShortcutsDest = Join-Path $KritaSupport "shortcuts"
$CssDest = Join-Path $KritaSupport "css_styles"
$PykritaDir = Join-Path $KritaSupport "pykrita"

Write-Host "Resource folder: $KritaSupport"

$required = @(
    (Join-Path $Root "plugin\hide_ui"),
    (Join-Path $Root "plugin\hide_ui.desktop"),
    (Join-Path $Root "config\krita5.xmlgui"),
    (Join-Path $Root "config\study_none.shortcuts"),
    (Join-Path $Root "scripts\patch_kritarc.ps1")
)
foreach ($p in $required) {
    if (-not (Test-Path $p)) {
        throw "Missing required pack file: $p`nUnzip the FULL study pack and keep the folder together."
    }
}

New-Item -ItemType Directory -Force -Path $PykritaDir | Out-Null
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

# UTF-8 no BOM — PowerShell Set-Content defaults to UTF-16 and breaks Python path reads
$dataRoot = Join-Path $Root "participant_data"
Write-Utf8NoBom (Join-Path $PluginDest "data_root.txt") $dataRoot

Copy-Item (Join-Path $Root "plugin\hide_ui.desktop") $PykritaDir -Force
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
$rcCandidates = @(Get-KritaRcCandidates)
$patched = @()
foreach ($prefs in $rcCandidates) {
    Write-Host "Patching kritarc: $prefs"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Patch -Prefs $prefs
    if (Test-StudyEnabled $prefs) {
        $patched += $prefs
        Write-Host "  OK enable_hide_ui=true"
    } else {
        Write-Host "  WARN: enable_hide_ui not confirmed in this file"
    }
}

$desktop = Join-Path $PykritaDir "hide_ui.desktop"
$pluginPy = Join-Path $PluginDest "hide_ui.py"
$dataRootFile = Join-Path $PluginDest "data_root.txt"

if (-not (Test-Path $PluginDest) -or -not (Test-Path $desktop) -or -not (Test-Path $pluginPy)) {
    throw "Study plugin files were not installed under $PykritaDir"
}
if (-not (Test-Path $dataRootFile)) {
    throw "data_root.txt missing after install."
}
$dataRootRead = [System.IO.File]::ReadAllText($dataRootFile).Trim()
if ($dataRootRead -ne $dataRoot) {
    throw "data_root.txt encoding/path mismatch.`nWrote: $dataRoot`nRead:  $dataRootRead"
}

$primaryRc = Join-Path $env:LOCALAPPDATA "kritarc"
if (-not (Test-StudyEnabled $primaryRc)) {
    # Store-only install: accept any patched store kritarc
    $anyOk = $false
    foreach ($p in $patched) {
        if (Test-StudyEnabled $p) { $anyOk = $true; break }
    }
    if (-not $anyOk) {
        throw @"
Could not enable the study plugin in the kritarc file Krita actually reads.

Expected setting in:
  $primaryRc

Patched candidates:
  $($rcCandidates -join "`n  ")

Open that file in Notepad and confirm it contains:
  [python]
  enable_hide_ui=true
"@
    }
}

Write-Host ""
Write-Host "Installed study plugin to:"
Write-Host "  $PluginDest"
Write-Host "Enabled study in kritarc:"
foreach ($p in $patched) { Write-Host "  $p" }
Write-Host "Participant data folder:"
Write-Host "  $dataRoot"

$kritaExe = Find-KritaExe
if ($kritaExe) {
    Write-Host "Found Krita:"
    Write-Host "  $kritaExe"
    # Expose for Launch Study.bat
    Set-Content -Path (Join-Path $Root ".krita_exe_path.txt") -Value $kritaExe -Encoding Ascii
} else {
    Write-Host "WARNING: krita.exe not found automatically. Install Krita, then open it from the Start menu after this install."
}

Write-Host "Install finished successfully."
