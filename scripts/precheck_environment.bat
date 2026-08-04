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
where adb
if errorlevel 1 (
  echo ERROR: adb not found on PATH. Set ANDROID_HOME or ADB_HOME.
  exit /b 1
)
adb start-server >nul 2>&1
adb devices
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
