@echo off
setlocal EnableExtensions

REM Args:
REM %1 = SUITE
REM %2 = FLOW_DIR
REM %3 = INCLUDE_TAG
REM %4 = APP_ID
REM %5 = CLEAR_STATE
REM %6 = MAESTRO_CMD

set "SUITE=%~1"
set "FLOW_DIR=%~2"
set "INCLUDE_TAG=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"
set "MAESTRO_CMD=%~6"

if "%SUITE%"=="" exit /b 10
if "%FLOW_DIR%"=="" exit /b 11
if "%APP_ID%"=="" exit /b 12
if "%CLEAR_STATE%"=="" set "CLEAR_STATE=true"
if "%MAESTRO_CMD%"=="" set "MAESTRO_CMD=maestro"
if "%AUTOFILL_RESTORE_AFTER_TEST%"=="" set "AUTOFILL_RESTORE_AFTER_TEST=0"

set "REPO_ROOT=%~dp0.."
for %%I in ("%REPO_ROOT%") do set "REPO_ROOT=%%~fI"
set "PS1=%REPO_ROOT%\scripts\run_suite_parallel_same_machine.ps1"

if not exist "%PS1%" (
    echo ERROR: Parallel runner PowerShell file not found: %PS1%
    exit /b 30
)

call "%REPO_ROOT%\scripts\set_maestro_java.bat" "%MAESTRO_CMD%" || exit /b 1

if defined MAESTRO_HOME (
    echo [INFO] PowerShell uses MAESTRO_HOME for Maestro: "%MAESTRO_HOME%maestro.bat" ^(or .cmd^)
)
echo [INFO] One ADB warm-up, then run_one in parallel: maestro --device ^<serial^> test ^<flow^>

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================
echo.
echo Suite: %SUITE%
echo Flow dir: %FLOW_DIR%
echo Include tag: %INCLUDE_TAG%
echo App id: %APP_ID%
echo Clear state: %CLEAR_STATE%
echo Autofill restore after test: %AUTOFILL_RESTORE_AFTER_TEST%
echo Maestro cmd: %MAESTRO_CMD%
echo Repo root: %REPO_ROOT%
echo PS runner: %PS1%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" ^
  -RepoRoot "%REPO_ROOT%" ^
  -Suite "%SUITE%" ^
  -FlowDir "%FLOW_DIR%" ^
  -IncludeTag "%INCLUDE_TAG%" ^
  -AppId "%APP_ID%" ^
  -ClearState "%CLEAR_STATE%" ^
  -MaestroCmd "%MAESTRO_CMD%"

set "FINAL_EXIT_CODE=%ERRORLEVEL%"
if not defined FINAL_EXIT_CODE set "FINAL_EXIT_CODE=1"

echo.
echo =====================================
echo FINAL RESULT FOR SUITE %SUITE% = %FINAL_EXIT_CODE%
echo =====================================

exit /b %FINAL_EXIT_CODE%
