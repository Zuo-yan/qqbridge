@echo off
setlocal
set "QQBRIDGE_ENTRY=%~dp0install-local.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& $env:QQBRIDGE_ENTRY"
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="3010" echo Restart Windows manually, then run install.cmd again.
if not "%CODE%"=="0" if not "%CODE%"=="3010" echo Installation stopped. See the message above. Existing data was preserved.
pause
exit /b %CODE%
