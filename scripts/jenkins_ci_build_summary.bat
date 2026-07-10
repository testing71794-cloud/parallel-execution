@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo ERROR: workspace required
  exit /b 1
)
cd /d "%~1"
set "WS_ROOT=%~1"
if not exist "%WS_ROOT%\build-summary" mkdir "%WS_ROOT%\build-summary"
pushd "%~dp0"
call "%~dp0jenkins_resolve_python.bat"
if errorlevel 1 (
  popd
  echo 1> "%WS_ROOT%\summary_failed.flag"
  exit /b 1
)
echo [DEBUG] "%PYTHON_EXE%" "%~dp0generate_build_summary.py" status build-summary
"%PYTHON_EXE%" "%~dp0generate_build_summary.py" status build-summary || (
  echo 1> "%WS_ROOT%\summary_failed.flag"
  popd
  exit /b 1
)
if exist "%~dp0generate_final_report.py" (
  "%PYTHON_EXE%" "%~dp0generate_final_report.py" "%WS_ROOT%" status "%WS_ROOT%\build-summary\final_execution_report.xlsx"
) else if exist "%WS_ROOT%\build-summary\final_execution_report.xlsx" (
  echo final_execution_report already from generate_excel merge.
) else (
  echo No generate_final_report.py; Excel merge should exist from per-suite report.
)
popd
exit /b 0
