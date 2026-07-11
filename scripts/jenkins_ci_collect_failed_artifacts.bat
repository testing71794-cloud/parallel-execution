@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo ERROR: workspace required
  exit /b 1
)
cd /d "%~1"
pushd "%~dp0"
call "%~dp0jenkins_resolve_python.bat"
if errorlevel 1 (
  popd
  exit /b 1
)
echo [collect-failed-artifacts] Running scripts\collect_failed_artifacts.py
"%PYTHON_EXE%" "%~dp0collect_failed_artifacts.py" "%~1"
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%
