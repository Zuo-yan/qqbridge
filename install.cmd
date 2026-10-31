@echo off
setlocal
cd /d "%~dp0"
fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
title QQBridge Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Yes
set "CODE=%ERRORLEVEL%"
echo.
if "%CODE%"=="0" (
    echo Installer finished. Follow the instructions in this window.
) else (
    echo Installer exited with code %CODE%. Please check the messages above.
)
echo.
pause
