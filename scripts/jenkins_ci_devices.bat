@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo ERROR: %~nx0 requires workspace root as first argument.
  exit /b 1
)
cd /d "%~1"
if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"
if not defined ANDROID_HOME if exist "C:\Tools\platform-tools\adb.exe" set "ANDROID_HOME=C:\Tools"
call "%~dp0windows_agent\list_devices.bat" "%~1" || (
  echo 1> "device_detection_failed.flag"
  echo 1> "pipeline_failed.flag"
  exit /b 1
)
exit /b 0
