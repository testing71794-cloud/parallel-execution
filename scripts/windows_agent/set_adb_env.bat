@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Resolve ADB_HOME only (device discovery). Does not modify JAVA_HOME / Maestro PATH.
REM script_rev=2026-05-windows-agent-adb-env-1

set "ADB_HOME="
set "ADB_EXE="

if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_HOME%\platform-tools"
if not defined ADB_HOME if defined ANDROID_SDK_ROOT if exist "%ANDROID_SDK_ROOT%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_SDK_ROOT%\platform-tools"
if not defined ADB_HOME if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%LOCALAPPDATA%\Android\Sdk\platform-tools"
if not defined ADB_HOME if exist "%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools"
if not defined ADB_HOME (
  for /f "delims=" %%W in ('where adb 2^>nul') do (
    for %%P in ("%%~dpW.") do set "ADB_HOME=%%~fP"
    goto :adb_ok
  )
)
:adb_ok
if defined ADB_HOME if exist "%ADB_HOME%\adb.exe" set "ADB_EXE=%ADB_HOME%\adb.exe"

if defined ADB_HOME echo ADB_HOME=%ADB_HOME%
if defined ADB_EXE echo ADB_EXE=%ADB_EXE%

endlocal & (
  set "ADB_HOME=%ADB_HOME%"
  set "ADB_EXE=%ADB_EXE%"
)
exit /b 0
