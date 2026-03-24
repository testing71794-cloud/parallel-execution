@echo off
setlocal EnableDelayedExpansion

echo =====================================
echo RUN AI ANALYSIS
echo =====================================

if not exist ai-doctor (
    echo ai-doctor folder not found. Skipping.
    exit /b 0
)

cd /d ai-doctor
call npm ci || call npm install
if errorlevel 1 exit /b 1

node index.mjs
if errorlevel 1 exit /b 1

exit /b 0
