# Quick Windows diagnostics for the Krita study pack.
# Run from the study-pack folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\diagnose-windows.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Krita Study Windows diagnostics ==="
Write-Host "Pack root: $Root"
Write-Host ""

$checks = @(
    @{ Name = "Primary kritarc (Krita reads this)"; Path = (Join-Path $env:LOCALAPPDATA "kritarc") },
    @{ Name = "Legacy/wrong kritarc"; Path = (Join-Path $env:APPDATA "krita\kritarc") },
    @{ Name = "Plugin folder"; Path = (Join-Path $env:APPDATA "krita\pykrita\hide_ui") },
    @{ Name = "Plugin desktop"; Path = (Join-Path $env:APPDATA "krita\pykrita\hide_ui.desktop") },
    @{ Name = "Plugin main py"; Path = (Join-Path $env:APPDATA "krita\pykrita\hide_ui\hide_ui.py") },
    @{ Name = "data_root.txt"; Path = (Join-Path $env:APPDATA "krita\pykrita\hide_ui\data_root.txt") },
    @{ Name = "Krita x64"; Path = (Join-Path $env:ProgramFiles "Krita (x64)\bin\krita.exe") },
    @{ Name = "Krita"; Path = (Join-Path $env:ProgramFiles "Krita\bin\krita.exe") }
)

foreach ($c in $checks) {
    $exists = Test-Path $c.Path
    Write-Host ("[{0}] {1}" -f ($(if ($exists) { "OK" } else { "MISSING" }), $c.Name))
    Write-Host ("      {0}" -f $c.Path)
    if ($exists -and $c.Path -like "*kritarc") {
        $raw = Get-Content -Raw -Path $c.Path -ErrorAction SilentlyContinue
        if ($raw -match "enable_hide_ui=true") {
            Write-Host "      enable_hide_ui=true FOUND"
        } else {
            Write-Host "      enable_hide_ui=true NOT FOUND"
        }
    }
    if ($exists -and $c.Name -eq "data_root.txt") {
        $bytes = [System.IO.File]::ReadAllBytes($c.Path)
        $bom = ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE)
        $text = [System.IO.File]::ReadAllText($c.Path).Trim()
        Write-Host ("      UTF-16 BOM: {0}" -f $bom)
        Write-Host ("      contents: {0}" -f $text)
    }
}

Write-Host ""
Write-Host "Store kritarc candidates:"
$pkgRoot = Join-Path $env:LOCALAPPDATA "Packages"
if (Test-Path $pkgRoot) {
    Get-ChildItem $pkgRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*Krita*" } |
        ForEach-Object {
            $rc = Join-Path $_.FullName "LocalCache\Local\kritarc"
            $ex = Test-Path $rc
            Write-Host ("[{0}] {1}" -f ($(if ($ex) { "OK" } else { "no" }), $rc))
            if ($ex) {
                $raw = Get-Content -Raw $rc -ErrorAction SilentlyContinue
                Write-Host ("      enable_hide_ui=true: {0}" -f ($raw -match "enable_hide_ui=true"))
            }
        }
} else {
    Write-Host "(no Packages folder)"
}

Write-Host ""
$procs = @(Get-Process -Name "krita*" -ErrorAction SilentlyContinue)
Write-Host ("Running Krita processes: {0}" -f $procs.Count)
Write-Host ""
Write-Host "Plugin log (if any): $env:USERPROFILE\krita_hide_ui_log.txt"
if (Test-Path (Join-Path $env:USERPROFILE "krita_hide_ui_log.txt")) {
    Write-Host "---- last 30 log lines ----"
    Get-Content (Join-Path $env:USERPROFILE "krita_hide_ui_log.txt") -Tail 30
}
Write-Host "=== end diagnostics ==="
