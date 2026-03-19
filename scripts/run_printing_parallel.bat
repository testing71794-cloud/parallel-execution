@echo off
setlocal enabledelayedexpansion

echo =====================================
echo DETECTING CONNECTED DEVICES
echo =====================================

if exist report_printing.xml del /f /q report_printing.xml
if exist reports_printing rmdir /s /q reports_printing
mkdir reports_printing

set COUNT=0

for /f "skip=1 tokens=1" %%D in ('adb devices') do (
    if not "%%D"=="" if not "%%D"=="List" if not "%%D"=="*" (
        set /a COUNT+=1
        set DEVICE!COUNT!=%%D
    )
)

echo Devices found: %COUNT%

if %COUNT% LEQ 0 (
    echo No devices found. Exiting...
    exit /b 1
)

echo =====================================
echo STARTING PARALLEL PRINTING FLOW EXECUTION
echo =====================================

for /L %%I in (1,1,%COUNT%) do (
    set CUR_DEVICE=!DEVICE%%I!
    echo Starting printing run for device: !CUR_DEVICE!

    mkdir "reports_printing\!CUR_DEVICE!" >nul 2>&1
    mkdir "reports_printing\!CUR_DEVICE!\output" >nul 2>&1

    start "PRINTING_!CUR_DEVICE!" cmd /c ^
        "maestro --device !CUR_DEVICE! test "Printing Flow" --format junit --output "reports_printing\!CUR_DEVICE!\report.xml" --test-output-dir "reports_printing\!CUR_DEVICE!\output" > "reports_printing\!CUR_DEVICE!\console.log" 2>&1 & echo !errorlevel! > "reports_printing\!CUR_DEVICE!\exit_code.txt""
)

echo =====================================
echo WAITING FOR ALL PRINTING RUNS TO COMPLETE
echo =====================================

:WAIT_LOOP
set DONE_COUNT=0

for /L %%I in (1,1,%COUNT%) do (
    set CUR_DEVICE=!DEVICE%%I!
    if exist "reports_printing\!CUR_DEVICE!\exit_code.txt" (
        set /a DONE_COUNT+=1
    )
)

if NOT "!DONE_COUNT!"=="%COUNT%" (
    timeout /t 5 /nobreak >nul
    goto WAIT_LOOP
)

echo All printing device runs completed.

echo =====================================
echo EVALUATING PRINTING RESULTS
echo =====================================

set OVERALL_EXIT=0
set FIRST_REPORT_COPIED=0

for /L %%I in (1,1,%COUNT%) do (
    set CUR_DEVICE=!DEVICE%%I!

    if exist "reports_printing\!CUR_DEVICE!\exit_code.txt" (
        set /p DEVICE_EXIT=<"reports_printing\!CUR_DEVICE!\exit_code.txt"
    ) else (
        set DEVICE_EXIT=1
    )

    echo Device !CUR_DEVICE! exit code: !DEVICE_EXIT!

    if not "!DEVICE_EXIT!"=="0" (
        set OVERALL_EXIT=1
    )

    if exist "reports_printing\!CUR_DEVICE!\report.xml" (
        echo Report generated for !CUR_DEVICE!

        if "!FIRST_REPORT_COPIED!"=="0" (
            copy /y "reports_printing\!CUR_DEVICE!\report.xml" "report_printing.xml" >nul
            set FIRST_REPORT_COPIED=1
            echo Root report_printing.xml created from device !CUR_DEVICE!
        )
    ) else (
        echo Report NOT generated for !CUR_DEVICE!
        set OVERALL_EXIT=1
    )
)

echo.
echo =====================================
echo PRINTING PARALLEL EXECUTION COMPLETE
echo Overall Exit Code: %OVERALL_EXIT%
echo =====================================

if exist report_printing.xml (
    echo Root report_printing.xml generated successfully
) else (
    echo Root report_printing.xml NOT generated
)

echo.
echo Generated per-device printing reports:
for /L %%I in (1,1,%COUNT%) do (
    set CUR_DEVICE=!DEVICE%%I!
    if exist "reports_printing\!CUR_DEVICE!\report.xml" (
        echo - reports_printing\!CUR_DEVICE!\report.xml
    )
)

exit /b %OVERALL_EXIT%