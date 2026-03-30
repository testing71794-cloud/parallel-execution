@echo off
setlocal enabledelayedexpansion

REM ===== FORCE JAVA =====
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo =====================================
echo JAVA DEBUG
echo =====================================
echo JAVA_HOME=%JAVA_HOME%
where java
java -version
where maestro
maestro --version
echo =====================================

REM ===== ORIGINAL LOGIC CONTINUES =====
set SUITE=%1
set FLOW_PATH=%2
set FLOW_NAME=%3
set DEVICE_ID=%4
set APP_ID=%5

if "%SUITE%"=="" exit /b 1
if "%FLOW_PATH%"=="" exit /b 1
if "%FLOW_NAME%"=="" exit /b 1
if "%DEVICE_ID%"=="" exit /b 1

echo Running %FLOW_NAME% on device %DEVICE_ID%

maestro --device "%DEVICE_ID%" test "%FLOW_PATH%"
exit /b %ERRORLEVEL%
