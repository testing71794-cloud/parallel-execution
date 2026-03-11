#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v node >/dev/null 2>&1 || { echo "❌ node not found (need Node 18+)"; exit 2; }
command -v adb  >/dev/null 2>&1 || { echo "⚠️  adb not found in PATH (screenshots/logcat/dumpsys may fail)"; }
command -v maestro >/dev/null 2>&1 || {
  if [ -x "$HOME/.maestro/bin/maestro" ]; then
    echo "ℹ️ maestro found at $HOME/.maestro/bin/maestro"
  else
    echo "⚠️  maestro not found in PATH (install maestro or ensure ~/.maestro/bin/maestro exists)"
  fi
}

node "$ROOT_DIR/ai-doctor/doctor.mjs"
