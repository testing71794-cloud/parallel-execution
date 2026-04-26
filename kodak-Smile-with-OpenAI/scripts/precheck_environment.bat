@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%set_maestro_java.bat" "%~1" || exit /b 1

set "JAVA_HOME=C:\Users\HP\.jdks\jbr-17.0.8"
set "MAESTRO_HOME=C:\Users\HP\maestro\maestro\bin"
set "ADB_HOME=C:\Users\HP\AppData\Local\Android\Sdk\platform-tools"
set "PATH=%JAVA_HOME%\bin;%MAESTRO_HOME%;%ADB_HOME%;%PATH%"

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
