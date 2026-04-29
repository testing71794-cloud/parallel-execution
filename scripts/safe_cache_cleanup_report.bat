@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Read-only report for npm / pip / Maestro / Jenkins paths. Does NOT delete anything.
REM Destructive cache commands appear only as REM lines at the bottom.

echo === Safe cache and disk report (no deletions) ===
echo.

call :size_mb "npm cache" "%LocalAppData%\npm-cache"
call :size_mb "pip cache" "%LocalAppData%\pip\Cache"

if exist "%USERPROFILE%\.maestro" (
  call :size_mb "User-dot-maestro" "%USERPROFILE%\.maestro"
) else (
  echo [size] User .maestro = not found
)

if defined WORKSPACE (
  if exist "%WORKSPACE%" call :size_mb "Jenkins WORKSPACE (env)" "%WORKSPACE%"
) else (
  echo [size] Jenkins WORKSPACE env = not set
)

if defined JENKINS_HOME (
  if exist "%JENKINS_HOME%" call :size_mb "JENKINS_HOME" "%JENKINS_HOME%"
) else (
  echo [size] JENKINS_HOME = not set - optional on agents
)

if exist "C:\JenkinsAgent" call :size_mb "C-JenkinsAgent-root" "C:\JenkinsAgent"

echo.
echo --- Optional destructive commands ^(do NOT run here; uncomment and run manually if needed^) ---
echo REM npm cache clean --force
echo REM pip cache purge
echo.
endlocal
exit /b 0

:size_mb
if "%~2"=="" exit /b 0
if not exist "%~2" (
  echo [size] %~1 = not found
  exit /b 0
)
set "CLN_PATH=%~2"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "if (Test-Path -LiteralPath $env:CLN_PATH) { $b = (Get-ChildItem -LiteralPath $env:CLN_PATH -Recurse -File -ErrorAction SilentlyContinue ^| Measure-Object Length -Sum).Sum; if ($null -eq $b) { '0' } else { [math]::Round($b/1MB,2).ToString() } } else { '0' }"`) do set "SZ=%%A"
echo [size] %~1 ~ !SZ! MB
set "CLN_PATH="
set "SZ="
exit /b 0
