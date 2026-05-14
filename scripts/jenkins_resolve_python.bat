@echo off
REM Resolve Python 3.11–3.13 for Jenkins Windows agents (rejects 3.14+; see jenkins_verify_python_toolchain.bat).
REM Optional (first match wins):
REM   PYTHON_EXE_OVERRIDE — full path to python.exe (same name as Linux / Jenkins job param).
REM   JENKINS_PYTHON_EXE   — same as override (legacy name).
REM   JENKINS_PYTHON_TAG   — if set, only py.exe -^<tag^> is tried (e.g. 3.12). If unset, tries 3.13, 3.12, 3.11.
REM Sets PYTHON_EXE in the caller's environment.

setlocal EnableExtensions EnableDelayedExpansion
set "PYSAVE="
set "PYTAG=3.11"
if defined JENKINS_PYTHON_TAG if not "!JENKINS_PYTHON_TAG!"=="" set "PYTAG=!JENKINS_PYTHON_TAG!"

if defined PYTHON_EXE_OVERRIDE (
  if exist "!PYTHON_EXE_OVERRIDE!" (
    set "PYSAVE=!PYTHON_EXE_OVERRIDE!"
    goto :finalize
  )
  echo ERROR: PYTHON_EXE_OVERRIDE set but file not found: !PYTHON_EXE_OVERRIDE!
  exit /b 1
)

if defined JENKINS_PYTHON_EXE (
  if exist "!JENKINS_PYTHON_EXE!" (
    set "PYSAVE=!JENKINS_PYTHON_EXE!"
    goto :finalize
  )
  echo ERROR: JENKINS_PYTHON_EXE not found: !JENKINS_PYTHON_EXE!
  exit /b 1
)

REM py.exe: single tag if JENKINS_PYTHON_TAG set; else try newest compatible first.
if defined JENKINS_PYTHON_TAG if not "!JENKINS_PYTHON_TAG!"=="" (
  where py >nul 2>&1 && for /f "delims=" %%I in ('py -!PYTAG! -c "import sys; print(sys.executable)" 2^>nul') do (
    set "PYSAVE=%%I"
    goto :finalize
  )
) else (
  for %%T in (3.13 3.12 3.11) do (
    where py >nul 2>&1 && for /f "delims=" %%I in ('py -%%T -c "import sys; print(sys.executable)" 2^>nul') do (
      set "PYSAVE=%%I"
      goto :finalize
    )
  )
)

REM Well-known install paths (python.org installers)
for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%ProgramFiles%\Python313\python.exe"
  "%ProgramFiles%\Python312\python.exe"
  "%ProgramFiles%\Python311\python.exe"
  "%ProgramFiles(x86)%\Python313\python.exe"
  "%ProgramFiles(x86)%\Python312\python.exe"
  "%ProgramFiles(x86)%\Python311\python.exe"
  "C:\Python313\python.exe"
  "C:\Python312\python.exe"
  "C:\Python311\python.exe"
) do (
  if exist %%~P (
    set "PYSAVE=%%~P"
    goto :finalize
  )
)

REM First python.exe on PATH with 3.11 <= version ^< 3.14
for /f "delims=" %%W in ('where python 2^>nul') do (
  "%%W" -c "import sys; raise SystemExit(0 if (3,11)<=sys.version_info<(3,14) else 1)" >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('"%%W" -c "import sys; print(sys.executable)" 2^>nul') do (
      set "PYSAVE=%%I"
      goto :finalize
    )
  )
)

echo ERROR: No Python 3.11–3.13 found ^(py.exe, standard install dirs, or PATH python^).
echo Tip: Install Python 3.12 or 3.13 from python.org ^(with "py launcher"^), OR set PYTHON_EXE_OVERRIDE / JENKINS_PYTHON_EXE to python.exe, OR set JENKINS_PYTHON_TAG=3.12 ^(etc.^) for py.exe.
exit /b 1

:finalize
if "!PYSAVE!"=="" exit /b 1
if not exist "!PYSAVE!" (
  echo ERROR: Candidate python missing: !PYSAVE!
  exit /b 1
)
for /f "delims=" %%V in ('"!PYSAVE!" -c "import sys; print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%V"
echo [python] "!PYSAVE!" ^(!PYVER!^)

for %%a in ("!PYSAVE!") do endlocal & set "PYTHON_EXE=%%~a"
exit /b 0
