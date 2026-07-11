@echo off
setlocal EnableExtensions
REM Start editing OpenRouter verify server for Maestro Studio (reads repo .env via Python).
set "REPO_ROOT=%~dp0..\..\.."
cd /d "%REPO_ROOT%"
if not exist "reports\editing" mkdir "reports\editing"
echo Starting editing verify server on http://127.0.0.1:8767
echo Close any older verify-server windows on port 8766 before running tests.
echo Leave this window open while running ED_* or PR_AI_* flows in Maestro Studio.
set "EDITING_VERIFY_PORT=8767"
set "OPENROUTER_SSL_VERIFY=0"
set "EDITING_VERIFY_PORT=8767"
if not defined OPENROUTER_MODEL_VISION set "OPENROUTER_MODEL_VISION=meta-llama/llama-3.2-11b-vision-instruct:free"
if defined OPENROUTER_API_KEY if not defined OpenRouterAPI set "OpenRouterAPI=%OPENROUTER_API_KEY%"
if exist "%REPO_ROOT%\.env" (
  echo Using OpenRouter key from %REPO_ROOT%\.env
) else (
  echo WARN: No .env at repo root. Copy .env.example to .env and set OPENROUTER_API_KEY.
)
py -3 "ATP TestCase Flows\Editing\scripts\editing_studio_verify_server.py"
