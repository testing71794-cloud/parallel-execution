Files updated:
- Jenkinsfile
- scripts/run_one_flow_on_device.bat
- scripts/run_suite_parallel_same_machine.ps1
- scripts/generate_excel_report.py
- scripts/generate_build_summary.py

Main fixes:
1. Per-device log, status, and result CSV are now mandatory.
2. Suite runner now fails if artifacts are missing.
3. Excel and summary generators now fail on zero completed results.
4. Jenkins now validates non-printing and printing artifacts before report generation.
5. Jenkins now passes CLEAR_STATE correctly instead of RETRY_FAILED.
6. Final build cannot become SUCCESS when no real device execution artifacts exist.
