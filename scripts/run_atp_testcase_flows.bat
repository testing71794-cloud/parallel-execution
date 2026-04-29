@echo off
setlocal EnableExtensions
REM ATP TestCase Flows runner (recursive yaml/yml). Does not replace Printing / Non-printing runners.
REM Args: APP_PACKAGE CLEAR_STATE MAESTRO_CMD [ATP_SUBFOLDER]
REM       Optional 4th arg runs only that child folder under "ATP TestCase Flows" (e.g. Camera, SignUp_Login).

set "RR=%~dp0.."
for %%I in ("%RR%") do set "RR=%%~fI"

if "%~4"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_atp_testcase_flows.ps1" -RepoRoot "%RR%" -AppId "%~1" -ClearState "%~2" -MaestroCmd "%~3"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_atp_testcase_flows.ps1" -RepoRoot "%RR%" -AppId "%~1" -ClearState "%~2" -MaestroCmd "%~3" -AtpSubfolder "%~4"
)
set "EC=%ERRORLEVEL%"
endlocal
exit /b %EC%
