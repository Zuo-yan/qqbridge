@echo off
setlocal
cd /d "%~dp0"
fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
title QQBridge Configure
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configure.ps1" -DiscoverGroups
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo Configure exited with code %CODE%.
echo.
pause
