@echo off
REM Shared Java selection for Maestro (JDK 17+). Call with: call scripts\set_maestro_java.bat
REM Optional: set JAVA_HOME_OVERRIDE first (e.g. Jenkins) to force a JDK root path.

if defined JAVA_HOME_OVERRIDE (
  if exist "%JAVA_HOME_OVERRIDE%\bin\java.exe" (
    set "JAVA_HOME=%JAVA_HOME_OVERRIDE%"
    goto :apply_path
  )
)

set "MAESTRO_JDK=C:\Program Files\Eclipse Adoptium\jdk-25.0.2.10-hotspot"
if exist "%MAESTRO_JDK%\bin\java.exe" (
  set "JAVA_HOME=%MAESTRO_JDK%"
  goto :apply_path
)

if defined JAVA_HOME (
  if exist "%JAVA_HOME%\bin\java.exe" (
    goto :apply_path
  )
)

echo ERROR: JDK 17+ not found. Set JAVA_HOME on the Jenkins agent, or set JAVA_HOME_OVERRIDE.
echo Tried: JAVA_HOME_OVERRIDE, %MAESTRO_JDK%, and existing JAVA_HOME.
exit /b 1

:apply_path
set "PATH=%JAVA_HOME%\bin;%PATH%"
exit /b 0
