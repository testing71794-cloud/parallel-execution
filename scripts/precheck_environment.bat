@echo off
setlocal

REM ===== FORCE JAVA =====
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"

echo =====================================
echo PRECHECK JAVA
echo =====================================
where java
java -version
echo =====================================

echo Checking Maestro...
where maestro
maestro --version

echo Precheck complete
exit /b 0
