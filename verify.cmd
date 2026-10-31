@echo off
setlocal
cd /d "%~dp0"
fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
title QQBridge Verify
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify.ps1"
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo Verification failed with code %CODE%.
echo.
pause
