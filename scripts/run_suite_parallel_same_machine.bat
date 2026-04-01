@echo off
call "%~dp0set_maestro_java.bat"

set FLOW_DIR=%1

for %%f in ("%FLOW_DIR%\*.yaml") do (
  echo Running %%f
  maestro test "%%f"
)
