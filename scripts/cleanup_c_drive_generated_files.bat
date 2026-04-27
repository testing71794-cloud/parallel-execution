@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Safe cleanup: generated data only. Never remove source, flows, elements, config, node_modules, or package trees.
REM Usage: cleanup_c_drive_generated_files.bat PRE^|POST [WORKSPACE]
if /I "%~1"=="" (
  echo [cleanup] USAGE: %~nx0 PRE^|POST [WORKSPACE]
  exit /b 0
)
set "MODE=%~1"
set "WS=%~2"
if not "%WS%"=="" (
  for %%I in ("%WS%") do set "WS=%%~fI"
) else if not "%WORKSPACE%"=="" (
  for %%I in ("%WORKSPACE%") do set "WS=%%~fI"
) else (
  for %%I in ("%~dp0..") do set "WS=%%~fI"
)
if not defined WS goto :done
if not exist "%WS%" goto :done

if /I not "%MODE%"=="PRE" if /I not "%MODE%"=="POST" (
  echo [cleanup] Unknown mode: %MODE%
  exit /b 0
)

if /I "%MODE%"=="PRE" call :maestro_pre_clean
if not exist "%WS%" goto :done

if defined WS if exist "%WS%" call :print_size "Workspace - before %MODE%" "%WS%"

if /I "%MODE%"=="PRE" (
  call :wipe_dir "%WS%\reports"
  call :wipe_dir "%WS%\logs"
  call :wipe_dir "%WS%\status"
  call :wipe_dir "%WS%\collected-artifacts"
  call :wipe_dir "%WS%\build-summary"
  call :wipe_dir "%WS%\.maestro"
  call :wipe_dir "%WS%\temp"
  call :wipe_dir "%WS%\temp-runners"
  call :wipe_dir "%WS%\ai-doctor\artifacts"
  if exist "%WS%\automation_with_testcases\logs" call :wipe_dir "%WS%\automation_with_testcases\logs"
  if exist "%WS%\automation_with_testcases\results" call :wipe_dir "%WS%\automation_with_testcases\results"
  del /q "%WS%\detected_devices.txt" 2>nul
  del /q "%WS%\*.flag" 2>nul
  del /q "%WS%\*.failed" 2>nul
  if not exist "%WS%\build-summary" mkdir "%WS%\build-summary" 2>nul
) else if /I "%MODE%"=="POST" (
  call :wipe_dir "%WS%\reports"
  call :wipe_dir "%WS%\logs"
  call :wipe_dir "%WS%\status"
  call :wipe_dir "%WS%\collected-artifacts"
  call :wipe_dir "%WS%\build-summary"
  call :wipe_dir "%WS%\.maestro"
  call :wipe_dir "%WS%\temp"
  call :wipe_dir "%WS%\temp-runners"
  call :wipe_dir "%WS%\ai-doctor\artifacts"
  if not exist "%WS%\build-summary" mkdir "%WS%\build-summary" 2>nul
)

if exist "%WS%" call :print_size "Workspace - after %MODE%" "%WS%"
:done
echo [cleanup] %MODE% done.
endlocal
exit /b 0

:maestro_pre_clean
call :print_size "Maestro user %USERPROFILE%\.maestro" "%USERPROFILE%\.maestro"
set "M=%USERPROFILE%\.maestro\tests"
if exist "%M%" ( echo [cleanup] Removing: "%M%" & rmdir /s /q "%M%" 2>nul )
set "M=%USERPROFILE%\.maestro\screenshots"
if exist "%M%" ( echo [cleanup] Removing: "%M%" & rmdir /s /q "%M%" 2>nul )
if not exist "C:\Windows\System32\config\systemprofile\.maestro" exit /b 0
call :print_size "Maestro LocalSystem .maestro" "C:\Windows\System32\config\systemprofile\.maestro"
set "M=C:\Windows\System32\config\systemprofile\.maestro\tests"
if exist "%M%" ( echo [cleanup] Removing: "%M%" & rmdir /s /q "%M%" 2>nul )
set "M=C:\Windows\System32\config\systemprofile\.maestro\screenshots"
if exist "%M%" ( echo [cleanup] Removing: "%M%" & rmdir /s /q "%M%" 2>nul )
exit /b 0

:wipe_dir
if "%~1"=="" exit /b 0
if not exist "%~1" exit /b 0
echo [cleanup] Removing: "%~1"
rmdir /s /q "%~1" 2>nul
if exist "%~1" ( echo [WARN] Could not fully remove: "%~1" & exit /b 0 )
exit /b 0

:print_size
if "%~2"=="" exit /b 0
if not exist "%~2" (
  echo [size] %~1 = not found
  exit /b 0
)
set "CLN_PATH=%~2"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "if (Test-Path -LiteralPath $env:CLN_PATH) { $b = (Get-ChildItem -LiteralPath $env:CLN_PATH -Recurse -Force -ErrorAction SilentlyContinue | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum; if ($null -eq $b) { 0 } else { [math]::Round(($b/1MB),2) } } else { 0 }"`) do set "SZ=%%A"
if not defined SZ set "SZ=0"
echo [size] %~1 = !SZ! MB
set "CLN_PATH="
set "SZ="
exit /b 0
