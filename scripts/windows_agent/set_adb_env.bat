@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Resolve ADB_HOME only (device discovery). Does not modify JAVA_HOME / Maestro PATH.
REM script_rev=2026-07-windows-agent-adb-env-2
REM Prefer C:\Tools\platform-tools (official zip). Avoid WinGet-only installs.
REM On this host default ADB port 5037 can hang; use 5038 unless already set.

set "ADB_HOME="
set "ADB_EXE="

if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"

if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_HOME%\platform-tools"
if not defined ADB_HOME if defined ANDROID_SDK_ROOT if exist "%ANDROID_SDK_ROOT%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_SDK_ROOT%\platform-tools"
if not defined ADB_HOME if exist "C:\Tools\platform-tools\adb.exe" set "ADB_HOME=C:\Tools\platform-tools"
if not defined ADB_HOME if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%LOCALAPPDATA%\Android\Sdk\platform-tools"
if not defined ADB_HOME if exist "%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools"
if not defined ADB_HOME (
  for /f "delims=" %%W in ('where adb 2^>nul') do (
    echo %%W | findstr /I /C:"WinGet" >nul
    if errorlevel 1 (
      for %%P in ("%%~dpW.") do set "ADB_HOME=%%~fP"
      goto :adb_ok
    )
  )
)
:adb_ok
if defined ADB_HOME if exist "%ADB_HOME%\adb.exe" set "ADB_EXE=%ADB_HOME%\adb.exe"

if defined ADB_HOME echo ADB_HOME=%ADB_HOME%
if defined ADB_EXE echo ADB_EXE=%ADB_EXE%
if defined ADB_SERVER_PORT echo ADB_SERVER_PORT=%ADB_SERVER_PORT%

endlocal & (
  set "ADB_HOME=%ADB_HOME%"
  set "ADB_EXE=%ADB_EXE%"
  set "ADB_SERVER_PORT=%ADB_SERVER_PORT%"
)
exit /b 0
