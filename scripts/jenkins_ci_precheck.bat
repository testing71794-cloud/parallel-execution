@echo off
setlocal EnableExtensions
REM Jenkins precheck: Java, ADB, Maestro (version via "maestro version" / "--version"), YAML.
REM Does not fail on "maestro --help" exit codes (some CLI builds return 1).
if "%~1"=="" (
  echo ERROR: workspace required
  exit /b 1
)
cd /d "%~1"
echo [precheck] workspace=%CD%
echo [precheck] MAESTRO_CMD=%~2
REM Prefer installed JDK 17 — set_maestro_java may still hardcode a missing jdk-25 on older SCM.
if not defined MAESTRO_JAVA_HOME (
  for /d %%D in ("C:\Program Files\Eclipse Adoptium\jdk-17*") do (
    if exist "%%~fD\bin\java.exe" set "MAESTRO_JAVA_HOME=%%~fD"
  )
)
if defined MAESTRO_JAVA_HOME echo [precheck] MAESTRO_JAVA_HOME=%MAESTRO_JAVA_HOME%
if defined ATP_MAESTRO_PARALLEL_HOME echo [precheck] ATP_MAESTRO_PARALLEL_HOME=%ATP_MAESTRO_PARALLEL_HOME%
if defined MAESTRO_HOME echo [precheck] MAESTRO_HOME=%MAESTRO_HOME%
echo =====================================
echo PRECHECK JAVA ^(quick^)
echo =====================================
where java
java -version
if errorlevel 1 (
  echo 1> "precheck_failed.flag"
  echo 1> "pipeline_failed.flag"
  exit /b 1
)
call "%~dp0precheck_environment.bat" "%~2" "%~3" || (
  echo 1> "precheck_failed.flag"
  echo 1> "pipeline_failed.flag"
  exit /b 1
)
exit /b 0
