@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

echo === Intelligent platform (parse + AI + cluster + report + email summary) ===
where python >nul 2>&1 || (
  echo python not on PATH — cannot run intelligent platform.
  exit /b 1
)

python -m intelligent_platform
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo intelligent platform exited with %ERR%
  exit /b %ERR%
)
echo Done.
exit /b 0
