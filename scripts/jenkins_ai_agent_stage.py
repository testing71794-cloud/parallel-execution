#!/usr/bin/env python3
"""
Jenkins entry for optional AI Step Print Agent stage.

Usage:
  python scripts/jenkins_ai_agent_stage.py <WORKSPACE> <APP_PACKAGE> <MAESTRO_CMD> [mode]

Exit codes:
  0 = success
  2 = partial/unstable (agent failures but stage completes)
  1 = hard failure (no devices, agent disabled unexpectedly)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def touch(name: str) -> None:
    (REPO / name).write_text("1\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 4:
        print(
            "Usage: jenkins_ai_agent_stage.py <WORKSPACE> <APP_PACKAGE> <MAESTRO_CMD> [mode]",
            file=sys.stderr,
        )
        return 2

    repo = Path(sys.argv[1]).resolve()
    app = sys.argv[2]
    maestro = sys.argv[3]
    mode = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("AI_AGENT_MODE", "assist")

    enabled = os.environ.get("AI_AGENT_ENABLED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if not enabled:
        print("[jenkins_ai_agent_stage] AI_AGENT_ENABLED=0 — skipping (no-op)", flush=True)
        return 0

    print(f"[jenkins_ai_agent_stage] starting mode={mode} app={app}", flush=True)
    agent_main = repo / "ai-agent" / "main.py"
    if not agent_main.is_file():
        print("[jenkins_ai_agent_stage] ai-agent/main.py not found", file=sys.stderr)
        touch("ai_agent_failed.flag")
        return 1

    env = os.environ.copy()
    env["AI_AGENT_ENABLED"] = "true"
    env["AI_AGENT_MODE"] = mode
    env["MAESTRO_CMD"] = maestro
    env.setdefault("PYTHONIOENCODING", "utf-8")

    cmd = [
        sys.executable,
        str(agent_main),
        "--repo",
        str(repo),
        "--mode",
        mode,
        "--maestro-cmd",
        maestro,
    ]
    proc = subprocess.run(cmd, cwd=str(repo), env=env, check=False)
    rc = proc.returncode

    if rc == 0:
        print("[jenkins_ai_agent_stage] status=SUCCESS", flush=True)
    elif rc == 2:
        touch("ai_agent_failed.flag")
        print("[jenkins_ai_agent_stage] status=UNSTABLE", flush=True)
    else:
        touch("ai_agent_failed.flag")
        print("[jenkins_ai_agent_stage] status=FAILED", flush=True)
    return rc if rc in (0, 2) else 2


if __name__ == "__main__":
    raise SystemExit(main())
