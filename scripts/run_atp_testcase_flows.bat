@echo off
setlocal EnableExtensions
REM ATP TestCase Flows runner (recursive yaml/yml). Does not replace Printing / Non-printing runners.
REM Args: APP_PACKAGE CLEAR_STATE MAESTRO_CMD

set "RR=%~dp0.."
for %%I in ("%RR%") do set "RR=%%~fI"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_atp_testcase_flows.ps1" -RepoRoot "%RR%" -AppId "%~1" -ClearState "%~2" -MaestroCmd "%~3"
set "EC=%ERRORLEVEL%"
endlocal
exit /b %EC%
