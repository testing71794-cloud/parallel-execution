@echo off
setlocal EnableExtensions
REM Run core editing flows on device ZA222RFQ75 (USB or wireless adb).
set "DEVICE=ZA222RFQ75"
set "APP=com.kodak.steptouch"
set "ROOT=%~dp0.."
cd /d "%ROOT%"

call "%ROOT%\scripts\precheck_environment.bat" || exit /b 1

set FLOWS=^
"ED_01 - Enter edit photo mode.yaml" ^
"ED_02 - Apply filter to photo.yaml" ^
"ED_05 - Adjust brightness.yaml" ^
"ED_11 - Add stickers to photo.yaml" ^
"ED_18 - Save edited image to gallery.yaml" ^
"ED_19 - Discard changes dont save.yaml" ^
"ED_E01 - Cancel edit without saving.yaml"

set PASS=0
set FAIL=0
for %%F in (%FLOWS%) do (
  echo.
  echo ===== %%F =====
  call "%ROOT%\scripts\run_one_flow_on_device.bat" editing "ATP TestCase Flows\editing\%%F" %DEVICE% %APP%
  if errorlevel 1 (
    set /a FAIL+=1
  ) else (
    set /a PASS+=1
  )
)
echo.
echo Editing smoke: PASS=%PASS% FAIL=%FAIL%
exit /b %FAIL%
