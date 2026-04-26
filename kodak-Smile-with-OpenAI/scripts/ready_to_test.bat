@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ready_to_test.ps1" %*
exit /b %ERRORLEVEL%
