#!/usr/bin/env bash
# Runs the production intelligence pipeline (does not re-run Maestro).
# Legacy tool that re-executed the whole suite: see scripts/deprecated_doctor_rerun_maestro.sh
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
if command -v python3 >/dev/null 2>&1; then
  exec python3 -m intelligent_platform "$@"
elif command -v python >/dev/null 2>&1; then
  exec python -m intelligent_platform "$@"
else
  echo "python3/python not found"
  exit 2
fi
