@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM script_rev=2026-07-set-maestro-java-portable-kodak-2
REM Optional %1 = Maestro launcher (MAESTRO_CMD): bare name or full path to maestro.bat / maestro.cmd
REM MAESTRO_JAVA_HOME = optional JDK for Maestro (Jenkins JAVA_HOME_OVERRIDE).
REM Prefer JDK 17 for Maestro; fall back to 21+. Never hardcode a missing JDK path.

REM --- Java ---
set "RESOLVED_JAVA="
if not "%MAESTRO_JAVA_HOME%"=="" (
  if exist "%MAESTRO_JAVA_HOME%\bin\java.exe" set "RESOLVED_JAVA=%MAESTRO_JAVA_HOME%"
)
REM Prefer Temurin 17 before inheriting JAVA_HOME (agents often have 21/8 as default)
if not defined RESOLVED_JAVA (
  for /d %%D in ("C:\Program Files\Eclipse Adoptium\jdk-17*") do (
    if exist "%%~fD\bin\java.exe" (
      set "RESOLVED_JAVA=%%~fD"
      goto :java_ok
    )
  )
)
if not defined RESOLVED_JAVA (
  for /d %%D in ("C:\Program Files\Microsoft\jdk-17*") do (
    if exist "%%~fD\bin\java.exe" (
      set "RESOLVED_JAVA=%%~fD"
      goto :java_ok
    )
  )
)
if not defined RESOLVED_JAVA if defined JAVA_HOME if exist "%JAVA_HOME%\bin\java.exe" (
  echo %JAVA_HOME% | findstr /I /C:"jdk-8" /C:"jre-1.8" /C:"\jre\\" >nul
  if errorlevel 1 set "RESOLVED_JAVA=%JAVA_HOME%"
)
if not defined RESOLVED_JAVA (
  for /d %%D in ("C:\Program Files\Eclipse Adoptium\jdk-21*") do (
    if exist "%%~fD\bin\java.exe" (
      set "RESOLVED_JAVA=%%~fD"
      goto :java_ok
    )
  )
)
if not defined RESOLVED_JAVA (
  for /d %%D in ("C:\Program Files\Eclipse Adoptium\jdk-*") do (
    if exist "%%~fD\bin\java.exe" (
      set "RESOLVED_JAVA=%%~fD"
      goto :java_ok
    )
  )
)
if not defined RESOLVED_JAVA if defined USERPROFILE if exist "%USERPROFILE%\.jdks" (
  for /d %%D in ("%USERPROFILE%\.jdks\jbr-17*") do (
    if exist "%%~fD\bin\java.exe" (
      set "RESOLVED_JAVA=%%~fD"
      goto :java_ok
    )
  )
)
:java_ok
if not defined RESOLVED_JAVA (
  echo ERROR: No JDK 17+ found. Install Temurin 17/21 or set MAESTRO_JAVA_HOME.
  endlocal & exit /b 1
)
set "JAVA_HOME=%RESOLVED_JAVA%"
if "%JAVA_HOME:~-1%"=="\" set "JAVA_HOME=%JAVA_HOME:~0,-1%"
if not exist "%JAVA_HOME%\bin\java.exe" (
  echo ERROR: Java not found at "%JAVA_HOME%"
  endlocal & exit /b 1
)

REM --- Maestro: directory that contains maestro.bat or maestro.cmd ---
REM Prefer ATP_MAESTRO_PARALLEL_HOME over MAESTRO_HOME when both are set (Jenkins parallel install).
if not "%ATP_MAESTRO_PARALLEL_HOME%"=="" (
  if exist "%ATP_MAESTRO_PARALLEL_HOME%\maestro.bat" (
    set "MAESTRO_HOME=%ATP_MAESTRO_PARALLEL_HOME%"
    goto :maestro_ok
  )
  if exist "%ATP_MAESTRO_PARALLEL_HOME%\maestro.cmd" (
    set "MAESTRO_HOME=%ATP_MAESTRO_PARALLEL_HOME%"
    goto :maestro_ok
  )
)

if not "%MAESTRO_HOME%"=="" (
  if exist "%MAESTRO_HOME%\maestro.bat" goto :maestro_ok
  if exist "%MAESTRO_HOME%\maestro.cmd" goto :maestro_ok
)

if not "%~1"=="" (
  if exist "%~f1" (
    for %%F in ("%~f1") do set "MAESTRO_HOME=%%~dpF"
    set "MAESTRO_HOME=!MAESTRO_HOME:~0,-1!"
    if exist "!MAESTRO_HOME!\maestro.bat" goto :maestro_ok
    if exist "!MAESTRO_HOME!\maestro.cmd" goto :maestro_ok
  )
)

set "MAESTRO_HOME=%USERPROFILE%\maestro\maestro\bin"
if exist "%MAESTRO_HOME%\maestro.bat" goto :maestro_ok
if exist "%MAESTRO_HOME%\maestro.cmd" goto :maestro_ok

set "MAESTRO_HOME=C:\Tools\maestro-parallel\bin"
if exist "%MAESTRO_HOME%\maestro.bat" goto :maestro_ok
if exist "%MAESTRO_HOME%\maestro.cmd" goto :maestro_ok

set "MAESTRO_HOME=C:\Tools\maestro\bin"
if exist "%MAESTRO_HOME%\maestro.bat" goto :maestro_ok
if exist "%MAESTRO_HOME%\maestro.cmd" goto :maestro_ok

set "MAESTRO_HOME=C:\maestro\maestro\bin"
if exist "%MAESTRO_HOME%\maestro.bat" goto :maestro_ok
if exist "%MAESTRO_HOME%\maestro.cmd" goto :maestro_ok

for /d %%D in ("C:\Tools\maestro*") do (
  if exist "%%~fD\bin\maestro.bat" (
    set "MAESTRO_HOME=%%~fD\bin"
    goto :maestro_ok
  )
  if exist "%%~fD\maestro\bin\maestro.bat" (
    set "MAESTRO_HOME=%%~fD\maestro\bin"
    goto :maestro_ok
  )
)

for /f "delims=" %%W in ('where maestro.bat 2^>nul') do (
  for %%P in ("%%~dpW.") do set "MAESTRO_HOME=%%~fP"
  goto :maestro_ok
)
for /f "delims=" %%W in ('where maestro.cmd 2^>nul') do (
  for %%P in ("%%~dpW.") do set "MAESTRO_HOME=%%~fP"
  goto :maestro_ok
)

if not "%~1"=="" (
  for /f "delims=" %%W in ('where "%~1" 2^>nul') do (
    for %%P in ("%%~dpW.") do set "MAESTRO_HOME=%%~fP"
    goto :maestro_ok
  )
)

echo ERROR: Maestro not found.
echo Set MAESTRO_HOME to the folder that contains maestro.bat, add Maestro to machine PATH,
echo or set the job parameter MAESTRO_CMD to the full path of maestro.bat.
echo When Jenkins runs as Local System, %%USERPROFILE%% is systemprofile — the default user install path does not apply.
endlocal & exit /b 1

:maestro_ok
set "PATH=%JAVA_HOME%\bin;%MAESTRO_HOME%;%PATH%"

REM --- ADB ---
if not defined ADB_SERVER_PORT set "ADB_SERVER_PORT=5038"
set "ADB_HOME="
if defined ANDROID_HOME if exist "%ANDROID_HOME%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_HOME%\platform-tools"
if not defined ADB_HOME if defined ANDROID_SDK_ROOT if exist "%ANDROID_SDK_ROOT%\platform-tools\adb.exe" set "ADB_HOME=%ANDROID_SDK_ROOT%\platform-tools"
if not defined ADB_HOME if exist "C:\Tools\platform-tools\adb.exe" set "ADB_HOME=C:\Tools\platform-tools"
if not defined ADB_HOME if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%LOCALAPPDATA%\Android\Sdk\platform-tools"
if not defined ADB_HOME if exist "%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe" set "ADB_HOME=%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools"
if not defined ADB_HOME (
  for /f "delims=" %%W in ('where adb 2^>nul') do (
    for %%P in ("%%~dpW.") do set "ADB_HOME=%%~fP"
    goto :adb_ok
  )
)
:adb_ok
if defined ADB_HOME set "PATH=%ADB_HOME%;%PATH%"

echo JAVA_HOME=%JAVA_HOME%
echo MAESTRO_HOME=%MAESTRO_HOME%
if defined ATP_MAESTRO_PARALLEL_HOME echo ATP_MAESTRO_PARALLEL_HOME=%ATP_MAESTRO_PARALLEL_HOME%
if defined ADB_HOME echo ADB_HOME=%ADB_HOME%
if defined ADB_SERVER_PORT echo ADB_SERVER_PORT=%ADB_SERVER_PORT%

endlocal & (
  set "JAVA_HOME=%JAVA_HOME%"
  set "MAESTRO_HOME=%MAESTRO_HOME%"
  set "ADB_HOME=%ADB_HOME%"
  set "ADB_SERVER_PORT=%ADB_SERVER_PORT%"
  set "PATH=%PATH%"
)
exit /b 0
