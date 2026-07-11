@echo off
REM Opt-in complete ATP suite — shared setup once, all modules, continue on failure.
setlocal
cd /d "%~dp0.."

set "APP=com.kodak.steptouch"
set "MAESTRO=maestro.bat"
if not "%~1"=="" set "APP=%~1"
if not "%~2"=="" set "MAESTRO=%~2"

python -m suite.test_suite_runner --repo "%CD%" --app-package "%APP%" --maestro-cmd "%MAESTRO%"
exit /b %ERRORLEVEL%
