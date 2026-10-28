@echo off
setlocal DisableDelayedExpansion
set "N2L_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%N2L_POWERSHELL%" (
    echo Windows PowerShell is unavailable. See docs\quickstart-windows.md.
    pause
    exit /b 2
)
if not exist "%~dp0scripts\start-gui.ps1" (
    echo Missing scripts\start-gui.ps1. Extract the complete project first.
    pause
    exit /b 2
)
start "" "%N2L_POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start-gui.ps1"
exit /b
