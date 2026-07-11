@echo off
setlocal
set REPO=%~dp0..
cd /d "%REPO%"
set AI_AGENT_ENABLED=1
set AI_AGENT_MODE=%~1
if "%AI_AGENT_MODE%"=="" set AI_AGENT_MODE=assist
python ai-agent\main.py --repo "%REPO%" --mode %AI_AGENT_MODE% --maestro-cmd maestro.bat
exit /b %ERRORLEVEL%
