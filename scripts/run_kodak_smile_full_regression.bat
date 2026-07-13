@echo off
REM Kodak Smile Full Regression — single command entry
setlocal EnableExtensions
set "REPO=%~dp0.."
cd /d "%REPO%"

set "AI_AGENT_ENABLED=1"
if "%~1"=="" (
  set "AI_AGENT_MODE=assist"
) else (
  set "AI_AGENT_MODE=%~1"
)

set "APP_PACKAGE=com.kodaksmile"
if not "%~2"=="" set "APP_PACKAGE=%~2"

set "MAESTRO_CMD=maestro.bat"
if not "%~3"=="" set "MAESTRO_CMD=%~3"

echo ============================================
echo  Kodak Smile Full Regression
echo  mode=%AI_AGENT_MODE% app=%APP_PACKAGE%
echo ============================================

python "%REPO%\ai-agent\main.py" --repo "%REPO%" --mode %AI_AGENT_MODE% --maestro-cmd "%MAESTRO_CMD%" --full-regression
exit /b %ERRORLEVEL%
