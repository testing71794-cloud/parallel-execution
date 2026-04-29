@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Safe workspace/runtime cleanup for automation. Does NOT delete sources, YAML, flows, elements, ATP cases, package.json, or Jenkinsfile.
REM Does NOT remove Jenkins archived builds under %%JENKINS_HOME%% (those are cleared via Jenkins UI / retention).
REM Delegates workspace deletes to cleanup_c_drive_generated_files.bat (PRE/POST/REPORT).
REM
REM Usage:
REM   safe_disk_cleanup.bat REPORT [WORKSPACE]
REM   safe_disk_cleanup.bat PRE [WORKSPACE]
REM   safe_disk_cleanup.bat POST [WORKSPACE]
REM
REM Optional destructive npm/pip trim (use rarely; slows next npm ci / pip install):
REM   set SAFE_DISK_CLEANUP_CONFIRM_CACHE=YES
REM   safe_disk_cleanup.bat PRE [WORKSPACE] CACHE

set "SDC_ROOT=%~dp0"

if /I "%~1"=="" goto :usage

if /I "%~1"=="REPORT" (
  call "%SDC_ROOT%cleanup_c_drive_generated_files.bat" REPORT "%~2"
  echo.
  echo === Extended report: check_disk_usage.ps1 ===
  if "%~2"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SDC_ROOT%check_disk_usage.ps1"
  ) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SDC_ROOT%check_disk_usage.ps1" -Workspace "%~2"
  )
  exit /b 0
)

if /I not "%~1"=="PRE" if /I not "%~1"=="POST" (
  echo [safe_disk_cleanup] Unknown mode: %~1
  goto :usage
)

call "%SDC_ROOT%cleanup_c_drive_generated_files.bat" %1 "%~2"
set "EC=!ERRORLEVEL!"

REM Optional: only when explicitly confirmed — clears npm/pip caches on the agent (not Jenkins archives).
if /I "%~1"=="PRE" if /I "%~3"=="CACHE" (
  if /I "!SAFE_DISK_CLEANUP_CONFIRM_CACHE!"=="YES" (
    echo [safe_disk_cleanup] SAFE_DISK_CLEANUP_CONFIRM_CACHE=YES: trimming npm and pip caches...
    where npm >nul 2>&1 && call npm cache clean --force
    where pip >nul 2>&1 && pip cache purge
    where py >nul 2>&1 && py -m pip cache purge 2>nul
  ) else (
    echo [safe_disk_cleanup] CACHE skipped: set SAFE_DISK_CLEANUP_CONFIRM_CACHE=YES to enable npm/pip cache trim.
  )
)

exit /b !EC!

:usage
echo Usage:
echo   %~nx0 REPORT [WORKSPACE]
echo   %~nx0 PRE [WORKSPACE] [CACHE]
echo   %~nx0 POST [WORKSPACE]
echo See docs/disk_cleanup_guide.md
exit /b 0
