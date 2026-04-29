@echo off
setlocal EnableExtensions
cd /d "%~1"
echo === GENERATE ATP TESTCASE EXCEL REPORTS ===
if exist build-summary\atp_suite_labels.json (
  python scripts/generate_atp_excel_reports.py . || (echo 1> atp_report_failed.flag)
) else (
  echo [ATP Excel] No atp_suite_labels.json - ATP had no flows or was skipped. OK.
)
