@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if exist "build-summary\ai_status.txt" findstr /C:"AI_STATUS=AVAILABLE" "build-summary\ai_status.txt" >nul && set "EXCEL_AI_OPENROUTER=1" || set "EXCEL_AI_OPENROUTER=0"
echo === Intelligent platform (EXCEL_AI_OPENROUTER=%EXCEL_AI_OPENROUTER%) ===
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
