#!/usr/bin/env python3
"""
Jenkins entry for optional complete ATP suite (single stage).

Usage:
  python scripts/jenkins_suite_stage.py <WORKSPACE> <APP_PACKAGE> <MAESTRO_CMD>

Exit codes (for catchError / flags):
  0 = all modules passed
  2 = partial failure (UNSTABLE — preferred)
  1 = setup failure or FAILURE mode
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from suite.test_suite_runner import run_complete_suite  # noqa: E402


def touch(name: str) -> None:
    (REPO / name).write_text("1\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 4:
        print(
            "Usage: jenkins_suite_stage.py <WORKSPACE> <APP_PACKAGE> <MAESTRO_CMD>",
            file=sys.stderr,
        )
        return 2
    repo = Path(sys.argv[1]).resolve()
    app = sys.argv[2]
    maestro = sys.argv[3]
    print("[jenkins_suite_stage] starting complete ATP suite", flush=True)
    ai_on = os.environ.get("ATP_AI_RECOVERY", "1").strip().lower() not in ("0", "false", "no", "off")
    print(f"[jenkins_suite_stage] AI recovery={'ON' if ai_on else 'OFF'}", flush=True)
    rc = run_complete_suite(repo, app_package=app, maestro_cmd=maestro)
    if rc == 0:
        print("[jenkins_suite_stage] suite_status=SUCCESS", flush=True)
    elif rc == 2:
        touch("suite_failed.flag")
        print("[jenkins_suite_stage] suite_status=UNSTABLE (partial module failures)", flush=True)
    else:
        touch("suite_failed.flag")
        print("[jenkins_suite_stage] suite_status=FAILED", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
