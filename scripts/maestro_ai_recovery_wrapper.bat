@echo off
REM Opt-in Maestro runner with AI recovery on failure only.
REM Does not replace Jenkins/ATP orchestrator unless explicitly wired.
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
  echo Usage: maestro_ai_recovery_wrapper.bat DEVICE FLOW_YAML [MODULE_NAME]
  echo   set ATP_AI_RECOVERY=1 ^(enabled by this wrapper^)
  exit /b 1
)

set "DEVICE=%~1"
set "FLOW=%~2"
set "MODULE=%~3"
set "ATP_AI_RECOVERY=1"

if "%MODULE%"=="" (
  python -m ai.maestro_integration --device "%DEVICE%" --flow "%FLOW%" --ai-recovery
) else (
  python -m ai.maestro_integration --device "%DEVICE%" --flow "%FLOW%" --module "%MODULE%" --ai-recovery
)
exit /b %ERRORLEVEL%
