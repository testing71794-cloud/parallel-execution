@echo off
setlocal

cd /d D:\Projects-Meastro\kodak-Smile-with-OpenAI

echo Detecting connected devices...
set COUNT=0

for /f "skip=1 tokens=1,2" %%A in ('adb devices') do (
    if "%%B"=="device" set /a COUNT+=1
)

echo Devices found: %COUNT%

if "%COUNT%"=="0" (
    echo No authorized devices found.
    pause
    exit /b 1
)

echo Running Non Printing Flows in parallel on %COUNT% device(s)...
maestro test "Non printing flows" --shard-all=%COUNT%

pause
endlocal