@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SUITE=%~1"
set "FLOW_DIR=%~2"
set "INCLUDE_TAG=%~3"
set "APP_ID=%~4"
set "CLEAR_STATE=%~5"

echo =====================================
echo RUN SUITE SAME MACHINE PARALLEL
echo =====================================

if not exist "reports" mkdir "reports"
if not exist "reports\%SUITE%" mkdir "reports\%SUITE%"
if not exist "reports\%SUITE%\logs" mkdir "reports\%SUITE%\logs"
if not exist "reports\%SUITE%\results" mkdir "reports\%SUITE%\results"

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\run_suite_parallel_same_machine.ps1" ^
  -Suite "%SUITE%" ^
  -FlowDir "%FLOW_DIR%" ^
  -IncludeTag "%INCLUDE_TAG%" ^
  -AppId "%APP_ID%" ^
  -ClearState "%CLEAR_STATE%"

exit /b %ERRORLEVEL%
