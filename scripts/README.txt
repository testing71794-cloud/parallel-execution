These are corrected replacement files for the Jenkins/Maestro parallel runner.

Files:
- run_suite_parallel_same_machine.bat
- run_suite_parallel_same_machine.ps1
- run_one_flow_on_device.bat

Execution order:
- For each flow file (flow1, flow2, …): run that flow on ALL devices in parallel, then move to the next flow.

Fixes:
- Uses absolute paths from the repo root
- Avoids the broken start/cmd/redirection pattern
- Avoids relative path failures inside PowerShell jobs
- Writes per-device logs and CSVs
