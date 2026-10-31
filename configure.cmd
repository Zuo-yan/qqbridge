@echo off
setlocal
set "QQBRIDGE_ENTRY=%~dp0configure.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& $env:QQBRIDGE_ENTRY -DiscoverGroups"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo Group configuration stopped. Check QQ login and preserve the existing instance.
pause
exit /b %CODE%
