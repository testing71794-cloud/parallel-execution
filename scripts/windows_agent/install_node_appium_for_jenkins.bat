@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Install Node.js + Appium for Jenkins (LocalSystem) — machine-wide paths.
REM Run elevated (Administrator) once per Windows Jenkins agent.
REM script_rev=2026-06-jenkins-node-appium-1
REM
REM Usage:
REM   scripts\windows_agent\install_node_appium_for_jenkins.bat
REM   scripts\windows_agent\install_node_appium_for_jenkins.bat "D:\Projects-Meastro\Kodak Step Print"

set "REPO_ROOT=%~1"
if "%REPO_ROOT%"=="" (
  for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
)
cd /d "%REPO_ROOT%"

set "NODE_DIR=C:\Program Files\nodejs"
set "NPM_GLOBAL=C:\Tools\npm-global"
set "NODE_MSI_URL=https://nodejs.org/dist/v20.11.1/node-v20.11.1-x64.msi"
set "NODE_MSI=%TEMP%\node-v20.11.1-x64.msi"

echo === Jenkins agent: Node.js + Appium setup ===
echo REPO_ROOT=%REPO_ROOT%
echo NODE_DIR=%NODE_DIR%
echo NPM_GLOBAL=%NPM_GLOBAL%

if not exist "%NODE_DIR%\node.exe" (
  echo [INFO] Node.js not found at "%NODE_DIR%" — downloading LTS MSI...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%NODE_MSI_URL%' -OutFile '%NODE_MSI%' -UseBasicParsing"
  if errorlevel 1 (
    echo ERROR: Failed to download Node.js MSI
    exit /b 1
  )
  echo [INFO] Installing Node.js silently ^(requires Administrator^)...
  msiexec /i "%NODE_MSI%" /qn ADDLOCAL=ALL
  if errorlevel 1 (
    echo ERROR: Node MSI install failed. Re-run this script as Administrator.
    exit /b 1
  )
  del "%NODE_MSI%" 2>nul
) else (
  echo [OK] Node.js already installed: "%NODE_DIR%\node.exe"
  "%NODE_DIR%\node.exe" -v
)

if not exist "%NODE_DIR%\node.exe" (
  echo ERROR: Node.js still missing after install attempt
  exit /b 1
)

echo [INFO] Adding Node.js to Machine PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$node='C:\Program Files\nodejs'; $npm='C:\Tools\npm-global'; $cur=[Environment]::GetEnvironmentVariable('Path','Machine'); $add=@($node,$npm) | Where-Object { $_ -and $cur -notlike ('*'+$_+'*') }; if ($add.Count) { [Environment]::SetEnvironmentVariable('Path', ($add -join ';') + ';' + $cur, 'Machine') }; [Environment]::SetEnvironmentVariable('NODE_HOME', $node, 'Machine'); [Environment]::SetEnvironmentVariable('NPM_GLOBAL', $npm, 'Machine'); Write-Host '[OK] Machine PATH and NODE_HOME updated'"

set "PATH=%NODE_DIR%;%NPM_GLOBAL%;%PATH%"
set "NODE_HOME=%NODE_DIR%"
set "NPM_GLOBAL=%NPM_GLOBAL%"

if not exist "%NPM_GLOBAL%" mkdir "%NPM_GLOBAL%" 2>nul

echo [INFO] npm global prefix -> %NPM_GLOBAL%
call "%NODE_DIR%\npm.cmd" config set prefix "%NPM_GLOBAL%" --global

echo [INFO] Installing Appium + UiAutomator2 driver globally...
call "%NODE_DIR%\npm.cmd" install -g appium@2.11.5
if errorlevel 1 (
  echo ERROR: npm install -g appium failed
  exit /b 1
)
set "APPIUM_SKIP_CHROMEDRIVER_INSTALL=1"
call "%NPM_GLOBAL%\appium.cmd" driver install uiautomator2@3.5.7
if errorlevel 1 (
  echo WARN: appium driver install failed — retry manually: appium driver install uiautomator2
)

set "MODULE_DIR=%REPO_ROOT%\automation\appium-gestures"
if exist "%MODULE_DIR%\package.json" (
  echo [INFO] npm install in %MODULE_DIR%
  pushd "%MODULE_DIR%"
  call "%NODE_DIR%\npm.cmd" install --no-fund --no-audit
  popd
)

echo.
echo === Verification ===
if exist "%NODE_DIR%\node.exe" echo [OK] node: %NODE_DIR%\node.exe
if exist "%NODE_DIR%\npm.cmd" echo [OK] npm: %NODE_DIR%\npm.cmd
if exist "%NPM_GLOBAL%\appium.cmd" (
  echo [OK] appium: %NPM_GLOBAL%\appium.cmd
  call "%NPM_GLOBAL%\appium.cmd" -v
) else (
  where appium 2>nul
)
if exist "%MODULE_DIR%\node_modules\webdriverio" (
  echo [OK] webdriverio present in appium-gestures module
) else (
  echo WARN: webdriverio missing in %MODULE_DIR%
)

echo.
echo [OK] Jenkins agent Node/Appium setup complete.
echo Restart Jenkins service so LocalSystem picks up Machine PATH:
echo   sc stop Jenkins ^&^& sc start Jenkins
exit /b 0
