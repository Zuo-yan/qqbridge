@echo off
setlocal
set "QQBRIDGE_ENTRY=%~dp0verify.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& $env:QQBRIDGE_ENTRY -RequireLogin"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo Verification incomplete. Check the FAIL items above.
pause
exit /b %CODE%
