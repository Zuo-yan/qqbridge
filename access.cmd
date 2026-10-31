@echo off
setlocal
set "QQBRIDGE_ENTRY=%~dp0access.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& $env:QQBRIDGE_ENTRY"
exit /b %ERRORLEVEL%
