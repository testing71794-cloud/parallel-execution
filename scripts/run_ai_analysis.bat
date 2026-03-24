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

call npm ci
if errorlevel 1 (
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed in ai-doctor.
        exit /b 1
    )
)

node index.mjs
if errorlevel 1 (
    echo ERROR: ai-doctor failed.
    exit /b 1
)

echo AI analysis completed.
exit /b 0
