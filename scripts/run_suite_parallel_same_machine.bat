@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE=%~1"
set "FLOW_DIR=%~2"
set "INCLUDE_TAG=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo.
echo Suite: %SUITE%
echo Flow dir: %FLOW_DIR%
echo Include tag: %INCLUDE_TAG%
echo App id: %APP_ID%
echo Clear state: %CLEAR_STATE%
echo Maestro cmd: %MAESTRO_CMD%
echo.

if "%SUITE%"=="" (
    echo ERROR: SUITE is required
    exit /b 1
)

if "%FLOW_DIR%"=="" (
    echo ERROR: FLOW_DIR is required
    exit /b 1
)

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

if not exist "%REPO_ROOT%\%FLOW_DIR%" (
    echo ERROR: Flow directory not found: %REPO_ROOT%\%FLOW_DIR%
    exit /b 1
)

if not exist "%REPO_ROOT%\reports" mkdir "%REPO_ROOT%\reports"
if not exist "%REPO_ROOT%\reports\%SUITE%" mkdir "%REPO_ROOT%\reports\%SUITE%"
if not exist "%REPO_ROOT%\reports\%SUITE%\logs" mkdir "%REPO_ROOT%\reports\%SUITE%\logs"
if not exist "%REPO_ROOT%\reports\%SUITE%\results" mkdir "%REPO_ROOT%\reports\%SUITE%\results"
if not exist "%REPO_ROOT%\status" mkdir "%REPO_ROOT%\status"

if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools" set "PATH=%ANDROID_HOME%\platform-tools;%PATH%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_suite_parallel_same_machine.ps1" ^
  -RepoRoot "%REPO_ROOT%" ^
  -Suite "%SUITE%" ^
  -FlowDir "%FLOW_DIR%" ^
  -IncludeTag "%INCLUDE_TAG%" ^
  -AppId "%APP_ID%" ^
  -ClearState "%CLEAR_STATE%" ^
  -MaestroCmd "%MAESTRO_CMD%"

set "RC=%ERRORLEVEL%"

echo.
echo =====================================
echo FINAL RESULT FOR SUITE %SUITE% = %RC%
echo =====================================

exit /b %RC%
