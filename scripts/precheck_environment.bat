@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%set_maestro_java.bat" || exit /b 1

echo =====================================
echo PRECHECK JAVA
echo =====================================
echo JAVA_HOME=%JAVA_HOME%
echo MAESTRO_HOME=%MAESTRO_HOME%
where java
java -version
if errorlevel 1 exit /b 1
echo =====================================

echo Checking ADB...
where adb
adb start-server >nul 2>&1
adb devices
if errorlevel 1 exit /b 1
echo =====================================

echo Checking Maestro...
where maestro
where maestro.bat
maestro --help >nul 2>&1
if errorlevel 1 exit /b 1
maestro --version
if errorlevel 1 exit /b 1

echo Precheck complete
exit /b 0
