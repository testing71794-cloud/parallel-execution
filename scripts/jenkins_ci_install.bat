@echo off
setlocal EnableExtensions
cd /d "%~1"
echo === SAFE DISK CLEANUP PRE ===
call scripts\safe_disk_cleanup.bat PRE "%CD%"
python -m pip install --upgrade pip || (echo 1> install_failed.flag & exit /b 1)
python -m pip install -r scripts/requirements-python.txt || (echo 1> install_failed.flag & exit /b 1)
if exist package.json (
  call npm ci || call npm install || (echo 1> install_failed.flag & exit /b 1)
)
if exist ai-doctor\package.json (
  cd ai-doctor
  call npm ci || call npm install || (echo 1> ..\install_failed.flag & exit /b 1)
  cd ..
)
if not exist build-summary mkdir build-summary
