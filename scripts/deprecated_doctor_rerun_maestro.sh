#!/usr/bin/env bash
# Legacy: re-run Maestro against the whole flows directory and then capture artifacts.
# Not used by Jenkins. Prefer CI-driven execution + intelligent_platform.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v node >/dev/null 2>&1 || { echo "node required"; exit 2; }
exec node "$ROOT_DIR/ai-doctor/doctor.mjs"
