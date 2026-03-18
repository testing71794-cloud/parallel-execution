@echo off
setlocal enabledelayedexpansion

echo =====================================
echo DETECTING CONNECTED DEVICES
echo =====================================

set COUNT=0

for /f "skip=1 tokens=1" %%D in ('adb devices') do (
    if not "%%D"=="" if not "%%D"=="List" (
        set /a COUNT+=1
    )
)

echo Devices found: %COUNT%

if %COUNT% LEQ 0 (
    echo ❌ No devices found. Exiting...
    exit /b 1
)

echo =====================================
echo RUNNING NON PRINTING FLOWS
echo =====================================

echo Running on %COUNT% device(s)...

REM Clean old report if exists
if exist report.xml del report.xml

REM Run Maestro with report generation
maestro test "Non printing flows" ^
  --shard-all=%COUNT% ^
  --format junit ^
  --output report.xml

set EXIT_CODE=%ERRORLEVEL%

echo =====================================
echo MAESTRO EXECUTION COMPLETE
echo Exit Code: %EXIT_CODE%
echo =====================================

REM Verify report.xml exists
if exist report.xml (
    echo ✅ report.xml generated successfully
) else (
    echo ❌ report.xml NOT generated
)

exit /b %EXIT_CODE%