@echo off
setlocal
cd /d "%~dp0"
fltmc >nul 2>&1
if errorlevel 1 (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
title QQBridge Installer
set "LOGDIR=%ProgramData%\QQBridge"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Transcript -Path (Join-Path $env:ProgramData 'QQBridge\install.log') -Append | Out-Null; try { & '%~dp0install.ps1' -Yes } finally { Stop-Transcript | Out-Null }"
set "CODE=%ERRORLEVEL%"
echo.
if "%CODE%"=="0" (
    echo Installer finished. Follow the instructions in this window.
) else (
    echo Installer exited with code %CODE%.
    echo Install log: "%LOGDIR%\install.log"
    echo Please send this log and the messages above to the maintainer.
)
echo.
pause
