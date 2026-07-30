$ErrorActionPreference = "Stop"
$KritaSupport = Join-Path $env:APPDATA "krita"
$Prefs = Join-Path $KritaSupport "kritarc"
Get-Process -Name "krita" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$PluginDest = Join-Path $KritaSupport "pykrita\hide_ui"
if (Test-Path $PluginDest) { Remove-Item -Recurse -Force $PluginDest }
foreach ($rel in @("pykrita\hide_ui.desktop", "krita5.xmlgui", "shortcuts\study_none.shortcuts", "css_styles\Study_Large_Text.svg")) {
    $f = Join-Path $KritaSupport $rel
    if (Test-Path $f) { Remove-Item -Force $f }
}
$Log = Join-Path $env:USERPROFILE "krita_hide_ui_log.txt"
if (Test-Path $Log) { Remove-Item -Force $Log }
if (Test-Path $Prefs) {
    $text = Get-Content -Raw -Path $Prefs
    if ($null -eq $text) { $text = "" }
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n"
    $text = [regex]::Replace($text, "(?m)^State=.*(?:\n|$)", "")
    $text = [regex]::Replace($text, "(?m)^DockWidget .*/DockArea=.*(?:\n|$)", "")
    if ($text -match "(?m)^showStatusBar=") {
        $text = [regex]::Replace($text, "(?m)^showStatusBar=.*$", "showStatusBar=true")
    } else {
        $text = $text.TrimEnd() + "`nshowStatusBar=true`n"
    }
    if ($text -match "(?m)^enable_hide_ui=") {
        $text = [regex]::Replace($text, "(?m)^enable_hide_ui=.*$", "enable_hide_ui=false")
    } elseif ($text -match "\[python\]") {
        $text = [regex]::Replace($text, "(\[python\])", "`$1`nenable_hide_ui=false")
    } else {
        $text = $text.TrimEnd() + "`n[python]`nenable_hide_ui=false`n"
    }
    if ($text -match "(?m)^Current Scheme=") {
        $text = [regex]::Replace($text, "(?m)^Current Scheme=.*$", "Current Scheme=Default")
    }
    [System.IO.File]::WriteAllText($Prefs, $text.Replace("`n", "`r`n"))
}
Write-Host ""
Write-Host "Study mode removed."
Write-Host "Open Krita again to use the normal version."
Write-Host ""
