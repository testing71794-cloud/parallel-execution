#!/usr/bin/env bash
# Post-run processing on GCP (Excel merge, summary, zip). Same Python entrypoints as Windows .bat wrappers.
set -euo pipefail
ROOT="${1:?Usage: jenkins_ci_post_reports.sh <repo-root>}"
cd "$ROOT"
export JENKINS_WORKLOAD_PROFILE="${JENKINS_WORKLOAD_PROFILE:-gcp-orchestrator}"
echo "[gcp-post] profile=${JENKINS_WORKLOAD_PROFILE} starting post-run processing"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_venv.sh
source "$SCRIPT_DIR/_venv.sh"
resolve_gcp_python "$ROOT"

if [[ -f build-summary/atp_suite_labels.json ]]; then
  echo "[gcp-post] merge ATP excel reports"
  "$PY" scripts/generate_atp_excel_reports.py . || echo 1 >atp_report_failed.flag
else
  echo "[gcp-post] no atp_suite_labels.json — skip ATP excel merge"
fi

echo "[gcp-post] build summary"
mkdir -p build-summary
"$PY" scripts/generate_build_summary.py status build-summary || echo 1 >summary_failed.flag
if [[ -f scripts/generate_final_report.py ]]; then
  "$PY" scripts/generate_final_report.py . status build-summary/final_execution_report.xlsx
fi

echo "[gcp-post] materialize execution_logs.zip"
"$PY" -c "import sys; from pathlib import Path; r=Path('.').resolve(); sys.path.insert(0, str(r)); from mailout.send_email import build_execution_logs_zip; z=build_execution_logs_zip(r); print('execution_logs.zip =>', z)"

echo "[gcp-post] collect failed logs/screenshots/videos for email + archive"
"$PY" scripts/collect_failed_artifacts.py "$ROOT" || echo "[WARN] collect_failed_artifacts failed — email may lack videos"

echo "[gcp-post] done"
