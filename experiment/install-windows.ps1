# Install study plugin into the current user's Krita profile (Windows).
# Critical: Krita reads %LOCALAPPDATA%\kritarc (NOT %APPDATA%\krita\kritarc).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $Root "install-log.txt"

function Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Write-Utf8NoBom([string]$Path, [string]$Text) {
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function Stop-KritaCompletely {
    Log "Stopping any running Krita processes..."
    for ($round = 1; $round -le 3; $round++) {
        $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ProcessName -match '^(krita|krita\.com)$'
        })
        if ($procs.Count -eq 0) { break }
        Log ("  round {0}: stopping {1} process(es)" -f $round, $procs.Count)
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    # Wait until fully gone so an exiting Krita cannot overwrite kritarc after we patch
    for ($i = 1; $i -le 40; $i++) {
        $left = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ProcessName -match '^(krita|krita\.com)$'
        })
        if ($left.Count -eq 0) {
            Log "Krita is fully closed."
            Start-Sleep -Seconds 1
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Could not fully close Krita. Open Task Manager, end krita.exe, then run Launch Study.bat again."
}

function Get-KritaResourceRoot {
    $roaming = Join-Path $env:APPDATA "krita"
    $rc = Join-Path $env:LOCALAPPDATA "kritarc"
    if (Test-Path $rc) {
        $raw = Get-Content -Raw -Path $rc -ErrorAction SilentlyContinue
        if ($raw -match "(?m)^ResourceDirectory=(.+)$") {
            $dir = $Matches[1].Trim().Replace("/", "\")
            if ($dir -and (Test-Path $dir)) {
                Log "Using ResourceDirectory from kritarc: $dir"
                return $dir
            }
        }
    }
    return $roaming
}

function Get-KritaRcCandidates {
    $list = New-Object System.Collections.Generic.List[string]
    $primary = Join-Path $env:LOCALAPPDATA "kritarc"
    if (-not $list.Contains($primary)) { [void]$list.Add($primary) }

    $pkgRoot = Join-Path $env:LOCALAPPDATA "Packages"
    if (Test-Path $pkgRoot) {
        Get-ChildItem -Path $pkgRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "49800Krita*" -or $_.Name -like "*Krita*" } |
            ForEach-Object {
                $storeRc = Join-Path $_.FullName "LocalCache\Local\kritarc"
                if (-not $list.Contains($storeRc)) { [void]$list.Add($storeRc) }
            }
    }

    $legacy = Join-Path $env:APPDATA "krita\kritarc"
    if (-not $list.Contains($legacy)) { [void]$list.Add($legacy) }
    return ,$list.ToArray()
}

function Test-StudyEnabled([string]$PrefsPath) {
    if (-not (Test-Path $PrefsPath)) { return $false }
    $raw = Get-Content -Raw -Path $PrefsPath -ErrorAction SilentlyContinue
    if ($null -eq $raw) { return $false }
    return [bool]($raw -match "enable_hide_ui\s*=\s*true")
}

function Find-KritaExe {
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {
        if ([string]::IsNullOrWhiteSpace($base)) { continue }
        [void]$candidates.Add((Join-Path $base "Krita (x64)\bin\krita.exe"))
        [void]$candidates.Add((Join-Path $base "Krita\bin\krita.exe"))
    }
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command "krita.exe" -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) { return $cmd.Source }
    return $null
}

function Invoke-PatchKritarc([string[]]$Paths) {
    $Patch = Join-Path $Root "scripts\patch_kritarc.ps1"
    $ok = @()
    foreach ($prefs in $Paths) {
        Log "Patching kritarc: $prefs"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Patch -Prefs $prefs
        if (Test-StudyEnabled $prefs) {
            Log "  OK: enable_hide_ui=true"
            $ok += $prefs
        } else {
            Log "  FAIL: enable_hide_ui missing after patch"
        }
    }
    return ,$ok
}

try {
    "" | Set-Content -Path $LogFile -Encoding UTF8
    Log "=== Krita Study install (Windows) ==="
    Log "Pack root: $Root"
    Log "LOCALAPPDATA: $env:LOCALAPPDATA"
    Log "APPDATA: $env:APPDATA"

    if (-not $env:LOCALAPPDATA) {
        throw "LOCALAPPDATA is empty. Cannot find Krita settings."
    }

    Stop-KritaCompletely

    $KritaSupport = Get-KritaResourceRoot
    $PluginDest = Join-Path $KritaSupport "pykrita\hide_ui"
    $ShortcutsDest = Join-Path $KritaSupport "shortcuts"
    $CssDest = Join-Path $KritaSupport "css_styles"
    $PykritaDir = Join-Path $KritaSupport "pykrita"
    Log "Resource folder: $KritaSupport"

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

    $dataRoot = Join-Path $Root "participant_data"
    Write-Utf8NoBom (Join-Path $PluginDest "data_root.txt") $dataRoot

    Copy-Item (Join-Path $Root "plugin\hide_ui.desktop") $PykritaDir -Force
    Copy-Item (Join-Path $Root "config\krita5.xmlgui") $KritaSupport -Force
    Copy-Item (Join-Path $Root "config\study_none.shortcuts") (Join-Path $ShortcutsDest "study_none.shortcuts") -Force

    New-Item -ItemType Directory -Force -Path $CssDest | Out-Null
    Copy-Item (Join-Path $Root "config\study_large_text.svg") (Join-Path $CssDest "Study_Large_Text.svg") -Force

    $ImgSrc = Join-Path $Root "images"
    if (Test-Path $ImgSrc) {
        $ImgDest = Join-Path $PluginDest "images"
        New-Item -ItemType Directory -Force -Path $ImgDest | Out-Null
        Copy-Item -Path (Join-Path $ImgSrc "*") -Destination $ImgDest -Recurse -Force
        Log "Copied images/"
    }

    $MediaSrc = Join-Path $Root "media"
    if (Test-Path $MediaSrc) {
        $MediaDest = Join-Path $PluginDest "media"
        New-Item -ItemType Directory -Force -Path $MediaDest | Out-Null
        Copy-Item -Path (Join-Path $MediaSrc "*") -Destination $MediaDest -Recurse -Force
        Get-ChildItem -Path $MediaDest -Recurse -Include *.mp4,*.mov,*.mkv,*.webm |
            Remove-Item -Force -ErrorAction SilentlyContinue
        Log "Copied media/ (videos excluded)"
    }

    Remove-Item (Join-Path $Root "layout_states\*.state") -Force -ErrorAction SilentlyContinue

    # Patch ONLY after Krita is fully dead (avoids kritarc wipe on quit)
    $rcCandidates = @(Get-KritaRcCandidates)
    $patched = @(Invoke-PatchKritarc $rcCandidates)

    $primaryRc = Join-Path $env:LOCALAPPDATA "kritarc"
    if (-not (Test-StudyEnabled $primaryRc) -and $patched.Count -eq 0) {
        throw @"
Could not enable study plugin in kritarc.

Primary file Krita reads:
  $primaryRc

Open it in Notepad and look for:
  enable_hide_ui=true

Log file:
  $LogFile
"@
    }

    $desktop = Join-Path $PykritaDir "hide_ui.desktop"
    $pluginPy = Join-Path $PluginDest "hide_ui.py"
    if (-not (Test-Path $pluginPy) -or -not (Test-Path $desktop)) {
        throw "Plugin files missing after copy under $PykritaDir"
    }

    $dataRootFile = Join-Path $PluginDest "data_root.txt"
    $dataRootRead = [System.IO.File]::ReadAllText($dataRootFile).Trim()
    if ($dataRootRead -ne $dataRoot) {
        throw "data_root.txt mismatch (encoding problem)."
    }

    # Final safety: patch primary again right before we finish
    if (Test-Path (Join-Path $Root "scripts\patch_kritarc.ps1")) {
        Log "Final re-patch of primary kritarc..."
        [void](Invoke-PatchKritarc @($primaryRc))
    }

    if (-not (Test-StudyEnabled $primaryRc) -and $patched.Count -eq 0) {
        throw "enable_hide_ui still missing in $primaryRc after final patch."
    }

    $kritaExe = Find-KritaExe
    if ($kritaExe) {
        Log "Found Krita: $kritaExe"
        Write-Utf8NoBom (Join-Path $Root ".krita_exe_path.txt") $kritaExe
    } else {
        Log "WARNING: krita.exe not found automatically."
    }

    Log "Installed plugin: $PluginDest"
    Log "Primary kritarc: $primaryRc"
    Log "enable_hide_ui in primary: $(Test-StudyEnabled $primaryRc)"
    Log "Install finished successfully."
    Write-Host ""
    Write-Host "SUCCESS. Plugin installed and study enabled."
    Write-Host "Log saved to: $LogFile"
    exit 0
}
catch {
    Log ("ERROR: " + $_.Exception.Message)
    Write-Host ""
    Write-Host "INSTALL FAILED."
    Write-Host $_.Exception.Message
    Write-Host "Log saved to: $LogFile"
    exit 1
}
