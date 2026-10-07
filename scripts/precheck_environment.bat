@echo off
setlocal EnableExtensions
REM Resolve Java/Maestro/ADB via set_maestro_java (no hardcoded user paths).
REM Args: %1 = MAESTRO_CMD (optional), %2 = app package (optional, unused here)

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%set_maestro_java.bat" "%~1" || exit /b 1

echo =====================================
echo PRECHECK JAVA
echo =====================================
echo JAVA_HOME=%JAVA_HOME%
echo MAESTRO_HOME=%MAESTRO_HOME%
if defined ADB_HOME echo ADB_HOME=%ADB_HOME%
where java
java -version
if errorlevel 1 exit /b 1
echo =====================================

echo Checking ADB...
if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"
set "ANDROID_ADB_SERVER_PORT=%ADB_SERVER_PORT%"
if not defined ADB_EXE (
  if defined ADB_HOME if exist "%ADB_HOME%\adb.exe" set "ADB_EXE=%ADB_HOME%\adb.exe"
)
if not defined ADB_EXE (
  where adb >nul 2>&1
  if errorlevel 1 (
    echo ERROR: adb not found on PATH. Set ANDROID_HOME or ADB_HOME.
    exit /b 1
  )
  set "ADB_EXE=adb"
)
echo ADB_EXE=%ADB_EXE%
echo ADB_SERVER_PORT=%ADB_SERVER_PORT%
REM Must use -P: stock adb ignores ADB_SERVER_PORT; default 5037 hangs / conflicts on this agent.
"%ADB_EXE%" -P %ADB_SERVER_PORT% start-server
if errorlevel 1 (
  echo ERROR: adb start-server failed on port %ADB_SERVER_PORT%
  exit /b 1
)
"%ADB_EXE%" -P %ADB_SERVER_PORT% devices
if errorlevel 1 exit /b 1
echo =====================================

echo Checking Maestro...
where maestro.bat 2>nul
where maestro.cmd 2>nul
where maestro 2>nul
REM Prefer official version flags; some Maestro builds return non-zero on --help.
maestro --version 2>nul
if errorlevel 1 maestro -v 2>nul
if errorlevel 1 maestro version 2>nul
if errorlevel 1 (
  echo ERROR: Maestro version check failed. Set MAESTRO_HOME or MAESTRO_CMD.
  exit /b 1
)

echo Precheck complete
exit /b 0
