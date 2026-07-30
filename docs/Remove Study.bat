@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0study-pack\uninstall-windows.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0study-pack\uninstall-windows.ps1"
) else if exist "%~dp0uninstall-windows.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-windows.ps1"
) else (
  echo Could not find uninstall-windows.ps1
  pause
  exit /b 1
)
if errorlevel 1 (
  echo Remove failed.
  pause
  exit /b 1
)
pause
endlocal
