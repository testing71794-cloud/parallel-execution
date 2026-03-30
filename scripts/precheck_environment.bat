@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%set_maestro_java.bat" || exit /b 1

echo =====================================
echo PRECHECK JAVA
echo =====================================
echo JAVA_HOME=%JAVA_HOME%
where java
java -version
if errorlevel 1 exit /b 1
echo =====================================

echo Checking Maestro...
where maestro
maestro --version
if errorlevel 1 exit /b 1

echo Precheck complete
exit /b 0
