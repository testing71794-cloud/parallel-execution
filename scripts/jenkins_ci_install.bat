@echo off
setlocal EnableExtensions
cd /d "%~1"
echo === SAFE DISK CLEANUP PRE ===
call scripts\safe_disk_cleanup.bat PRE "%CD%"

REM Use the same Python 3.11–3.13 resolution as other Jenkins scripts. Bare "python" may hit
REM a broken install (e.g. Python 3.14 preview with corrupted pip on PATH).
call scripts\jenkins_resolve_python.bat
if errorlevel 1 (
  echo ERROR: jenkins_resolve_python.bat failed — install Python 3.12/3.13 or set PYTHON_EXE_OVERRIDE.
  echo 1> install_failed.flag
  exit /b 1
)
if not defined PYTHON_EXE (
  echo ERROR: PYTHON_EXE not set after jenkins_resolve_python.bat
  echo 1> install_failed.flag
  exit /b 1
)
echo [install] Using PYTHON_EXE=%PYTHON_EXE%

"%PYTHON_EXE%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [install] pip not usable; trying ensurepip...
  "%PYTHON_EXE%" -m ensurepip --upgrade
  if errorlevel 1 (
    echo ERROR: ensurepip failed for "%PYTHON_EXE%"
    echo 1> install_failed.flag
    exit /b 1
  )
)

"%PYTHON_EXE%" -m pip install --upgrade pip || (echo 1> install_failed.flag & exit /b 1)
"%PYTHON_EXE%" -m pip install -r scripts/requirements-python.txt || (echo 1> install_failed.flag & exit /b 1)
if exist package.json (
  call npm ci || call npm install || (echo 1> install_failed.flag & exit /b 1)
)
if exist ai-doctor\package.json (
  cd ai-doctor
  call npm ci || call npm install || (echo 1> ..\install_failed.flag & exit /b 1)
  cd ..
)
if not exist build-summary mkdir build-summary
