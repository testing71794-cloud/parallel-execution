@echo off
call "%~dp0set_maestro_java.bat"

echo =====================================
echo PRECHECK JAVA
echo =====================================
where java
java -version

echo =====================================
echo Checking Maestro...
where maestro
where maestro.bat
maestro --version || exit /b 1
