@echo off

setlocal EnableExtensions

REM Run GA_02 only via the same path as Jenkins Gallery stage (OpenRouter from env/credentials).

REM On Jenkins: Build with Parameters -> RUN_ATP_GALLERY=true, ATP_FLOW_INCLUDE=GA_02

REM Local agent (set OPENROUTER_API_KEY first, or use repo .env):

REM   scripts\jenkins_run_ga02.bat



set "REPO_ROOT=%~dp0.."

cd /d "%REPO_ROOT%"



set "ATP_FLOW_INCLUDE=GA_02"

if not defined OPENROUTER_MODEL_VISION set "OPENROUTER_MODEL_VISION=openai/gpt-4.1-mini"

if defined OPENROUTER_API_KEY if not defined OpenRouterAPI set "OpenRouterAPI=%OPENROUTER_API_KEY%"

set "MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS=1"

set "MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_CLASS_LOOKUP=1"



set "APP=%~1"

if "%APP%"=="" set "APP=com.kodak.steptouch"

set "MAESTRO=%~2"

if "%MAESTRO%"=="" set "MAESTRO=maestro.bat"

set "CLEAR=%~3"

if "%CLEAR%"=="" set "CLEAR=false"



echo [GA_02] ATP_FLOW_INCLUDE=%ATP_FLOW_INCLUDE% OPENROUTER_MODEL_VISION=%OPENROUTER_MODEL_VISION%

call "%REPO_ROOT%\scripts\start_maestro_verify_server_background.bat"

if errorlevel 1 echo [GA_02] WARN: verify server did not start; GraalJS adb fallback may still work

python scripts\jenkins_atp_stage.py all gallery "%APP%" "%CLEAR%" "%MAESTRO%"

exit /b %ERRORLEVEL%

