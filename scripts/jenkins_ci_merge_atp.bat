@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo ERROR: workspace required
  exit /b 1
)
cd /d "%~1"
set "WS_ROOT=%~1"
echo === GENERATE ATP TESTCASE EXCEL REPORTS ===
pushd "%~dp0"
call "%~dp0jenkins_resolve_python.bat"
if errorlevel 1 (
  popd
  exit /b 1
)
if exist "%WS_ROOT%\build-summary\atp_suite_labels.json" (
  echo [DEBUG] "%PYTHON_EXE%" "%~dp0generate_atp_excel_reports.py" "%WS_ROOT%"
  "%PYTHON_EXE%" "%~dp0generate_atp_excel_reports.py" "%WS_ROOT%" || (
    echo 1> "%WS_ROOT%\atp_report_failed.flag"
    popd
    exit /b 1
  )
) else (
  echo [ATP Excel] No atp_suite_labels.json - ATP had no flows or was skipped. OK.
)
popd
exit /b 0
