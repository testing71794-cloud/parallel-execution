@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo ERROR: %~nx0 requires workspace root as first argument.
  exit /b 1
)
cd /d "%~1"
echo === SAFE DISK CLEANUP PRE (before Maestro run) ===
call "%~dp0safe_disk_cleanup.bat" PRE "%CD%"
set "EC=%ERRORLEVEL%"
echo === TEMP Maestro APK cleanup ===
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cleanup_temp_maestro_apks.ps1"
exit /b %EC%
