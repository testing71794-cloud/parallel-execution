@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM script_rev=2026-10-windows-agent-list-devices-utf8-parse-4
REM Writes detected_devices.txt under the Jenkins workspace (paths may contain spaces).
REM Force ADB_SERVER_PORT=5038 - default 5037 hangs on CA Global agent.
REM Reuse existing ADB on 5038 across ATP modules - no double bind 10048.
REM Parse device serials in PowerShell (UTF-8 safe). Avoid cmd for /f on UTF-16 dumps.
goto :script_body

REM Sleep without timeout.exe (Jenkins non-TTY safe).
:sleep_seconds
set /a "_ss=%~1"
if !_ss! LSS 1 set "_ss=1"
if !_ss! GTR 120 set "_ss=120"
set /a "_ss_ping=!_ss!+1"
ping 127.0.0.1 -n !_ss_ping! >nul
exit /b 0

:script_body
REM Optional %1 = workspace root; else WORKSPACE env; else parent of scripts\.
set "REPO_ROOT="
if not "%~1"=="" (
  for %%I in ("%~1") do set "REPO_ROOT=%%~fI"
) else if not "%WORKSPACE%"=="" (
  for %%I in ("%WORKSPACE%") do set "REPO_ROOT=%%~fI"
) else (
  set "SCRIPT_DIR=%~dp0"
  for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"
)
if not defined REPO_ROOT (
  echo ERROR: REPO_ROOT not resolved. Pass workspace as arg1 or set WORKSPACE.
  exit /b 1
)
cd /d "%REPO_ROOT%"

if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"

set "OUT_FILE=%REPO_ROOT%\detected_devices.txt"
REM Prefer %%TEMP%% for intermediates to avoid workspace file locks.
set "ADB_DEVICES_TMP=%TEMP%\kodak_adb_devices_%RANDOM%.txt"

echo =====================================
echo LIST DEVICES (windows_agent)
echo =====================================
echo script_rev        : 2026-10-windows-agent-list-devices-utf8-parse-4
echo arg1 workspace    : %~1
echo WORKSPACE env     : %WORKSPACE%
echo REPO_ROOT         : %REPO_ROOT%
echo CD                : %CD%
echo OUT_FILE          : %OUT_FILE%
echo ADB_SERVER_PORT   : %ADB_SERVER_PORT%
echo =====================================

call "%~dp0set_adb_env.bat"
if errorlevel 1 (
  echo ERROR: set_adb_env.bat failed
  exit /b 1
)
if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"

if exist "%~dp0..\set_maestro_java.bat" (
  call "%~dp0..\set_maestro_java.bat" >nul 2>&1
)
if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"

if not defined ADB_DETECT_WAIT_ATTEMPTS set "ADB_DETECT_WAIT_ATTEMPTS=4"
if not defined ADB_DETECT_WAIT_SECS set "ADB_DETECT_WAIT_SECS=3"

echo =========================
echo Connected Android devices
echo =========================

if not defined ADB_EXE (
  if defined ADB_HOME if exist "%ADB_HOME%\adb.exe" set "ADB_EXE=%ADB_HOME%\adb.exe"
)
if not defined ADB_EXE if exist "C:\Tools\platform-tools\adb.exe" set "ADB_EXE=C:\Tools\platform-tools\adb.exe"
if not defined ADB_EXE (
  echo ERROR: adb.exe not found. Set ANDROID_HOME or add platform-tools to PATH.
  exit /b 1
)
echo ADB_EXE="%ADB_EXE%"
echo ADB_SERVER_PORT=%ADB_SERVER_PORT%

set "ADB_TIMEOUT_PS=%~dp0adb_run_timeout.ps1"
set "PARSE_PS=%~dp0parse_adb_devices.ps1"
if not exist "%ADB_TIMEOUT_PS%" (
  echo ERROR: missing "%ADB_TIMEOUT_PS%"
  exit /b 1
)
if not exist "%PARSE_PS%" (
  echo ERROR: missing "%PARSE_PS%"
  exit /b 1
)

del /q "%OUT_FILE%" 2>nul

set /a "_ATT=0"
:detect_loop
set /a "_ATT+=1"
echo.
echo [detect] attempt !_ATT!/%ADB_DETECT_WAIT_ATTEMPTS% (wait %ADB_DETECT_WAIT_SECS%s)

REM Only restart ADB on later attempts - early kills race with device enumeration.
if !_ATT! GEQ 3 (
  echo [detect] restarting ADB server...
  taskkill /F /IM adb.exe /T >nul 2>&1
  call :sleep_seconds 2
)

echo Starting/reusing ADB server on port %ADB_SERVER_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ADB_TIMEOUT_PS%" -AdbExe "%ADB_EXE%" -AdbArgs start-server -TimeoutSec 8
powershell -NoProfile -ExecutionPolicy Bypass -File "%ADB_TIMEOUT_PS%" -AdbExe "%ADB_EXE%" -EnsureServer
call :sleep_seconds 1

del /q "%ADB_DEVICES_TMP%" 2>nul
echo --- adb devices (full output, timeout 25s, port %ADB_SERVER_PORT%) ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%ADB_TIMEOUT_PS%" -AdbExe "%ADB_EXE%" -AdbArgs devices -TimeoutSec 25 -OutFile "%ADB_DEVICES_TMP%"
if not exist "%ADB_DEVICES_TMP%" (
  echo. > "%ADB_DEVICES_TMP%"
)
echo --- end adb devices ---

set "COUNT=0"
for /f "usebackq delims=" %%C in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%PARSE_PS%" -InFile "%ADB_DEVICES_TMP%" -OutFile "%OUT_FILE%"`) do set "COUNT=%%C"
if not defined COUNT set "COUNT=0"
echo !COUNT!| findstr /r "^[0-9][0-9]*$" >nul || set "COUNT=0"

if !COUNT! GTR 0 goto :detect_done

if !_ATT! LSS %ADB_DETECT_WAIT_ATTEMPTS% (
  echo [WARN] No device in state "device" yet; waiting %ADB_DETECT_WAIT_SECS%s...
  call :sleep_seconds %ADB_DETECT_WAIT_SECS%
  goto :detect_loop
)

echo.
echo Devices detected: 0
echo Device list saved to: "%OUT_FILE%"
del /q "%ADB_DEVICES_TMP%" 2>nul
exit /b 1

:detect_done
echo.
echo Devices detected: !COUNT!
echo Device list saved to: "%OUT_FILE%"
echo [DEBUG] list_devices OK - wrote "%OUT_FILE%"
type "%OUT_FILE%"
REM Do not del temp here — locked files can hang Jenkins bat after success.
echo [DEBUG] list_devices exit=0
exit /b 0
