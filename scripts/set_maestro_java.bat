@echo off
setlocal EnableExtensions

REM Force Java 25 + user-installed Maestro location
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
set "MAESTRO_HOME=%USERPROFILE%\maestro\maestro\bin"

if not exist "%JAVA_HOME%\bin\java.exe" (
  echo ERROR: Java not found at %JAVA_HOME%
  endlocal & exit /b 1
)

if not exist "%MAESTRO_HOME%\maestro.bat" (
  echo ERROR: Maestro not found at %MAESTRO_HOME%\maestro.bat
  endlocal & exit /b 1
)

set "PATH=%JAVA_HOME%\bin;%MAESTRO_HOME%;%PATH%"
echo JAVA_HOME=%JAVA_HOME%
echo MAESTRO_HOME=%MAESTRO_HOME%

endlocal & (
  set "JAVA_HOME=%JAVA_HOME%"
  set "MAESTRO_HOME=%MAESTRO_HOME%"
  set "PATH=%PATH%"
)
exit /b 0
