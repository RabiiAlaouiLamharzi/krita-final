param(
    [Parameter(Mandatory = $true)]
    [string]$Prefs
)

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $Prefs
if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
if (-not (Test-Path $Prefs)) {
    New-Item -ItemType File -Force -Path $Prefs | Out-Null
}

$text = Get-Content -Raw -Path $Prefs -ErrorAction SilentlyContinue
if ($null -eq $text) { $text = "" }
$text = $text -replace "`r`n", "`n" -replace "`r", "`n"
$text = [regex]::Replace($text, "(?m)^State=.*(?:\n|$)", "")

function Set-Root([string]$key, [string]$value) {
    $script:text = [regex]::Replace($script:text, "(?m)^$([regex]::Escape($key))=.*$", "$key=$value")
    if ($script:text -notmatch "(?m)^$([regex]::Escape($key))=") {
        $script:text = $script:text.TrimEnd() + "`n$key=$value`n"
    }
}

function Set-Section([string]$section, [string]$key, [string]$value) {
    $header = "[$section]"
    if ($script:text -notmatch [regex]::Escape($header)) {
        $script:text = $script:text.TrimEnd() + "`n$header`n"
    }
    $pattern = "(?s)(\[$([regex]::Escape($section))\])([^\[]*)"
    $m = [regex]::Match($script:text, $pattern)
    if (-not $m.Success) {
        $script:text = $script:text.TrimEnd() + "`n$header`n$key=$value`n"
        return
    }
    $body = $m.Groups[2].Value
    if ($body -match "(?m)^$([regex]::Escape($key))=") {
        $body = [regex]::Replace($body, "(?m)^$([regex]::Escape($key))=.*$", "$key=$value")
    } else {
        $body = $body.TrimEnd() + "`n$key=$value`n"
    }
    $script:text = $script:text.Substring(0, $m.Index) + $header + $body + $script:text.Substring($m.Index + $m.Length)
}

Set-Root "showStatusBar" "false"
Set-Root "toolbarslider_1" "size"
Set-Section "MainWindow" "toolOptionsInDocker" "false"
Set-Section "MainWindow" "newCursorStyle" "2"
Set-Section "python" "enable_hide_ui" "true"
Set-Section "SelectedTags" "paintoppreset" "All"
Set-Section "SvgTextTool" "useCurrentTextProperties" "true"
Set-Section "SvgTextTool" "cssStylePresetName" ""
Set-Section "Shortcut Schemes" "Current Scheme" "study_none"

$dockers = @(
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
    "TextProperties"
)
foreach ($name in $dockers) {
    Set-Section "MainWindow" ("DockWidget {0}/DockArea" -f $name) "256"
}

[System.IO.File]::WriteAllText($Prefs, $text.Replace("`n", "`r`n"))
Write-Host "Updated $Prefs"
