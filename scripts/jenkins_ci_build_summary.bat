@echo off
setlocal EnableExtensions
cd /d "%~1"
if not exist build-summary mkdir build-summary
python scripts/generate_build_summary.py status build-summary || (echo 1> summary_failed.flag)
if exist scripts\generate_final_report.py (
  python scripts/generate_final_report.py . status build-summary\final_execution_report.xlsx
) else if exist build-summary\final_execution_report.xlsx (
  echo final_execution_report already from generate_excel merge.
) else (
  echo No generate_final_report.py; Excel merge should exist from per-suite report.
)
