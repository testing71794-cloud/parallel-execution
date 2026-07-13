#!/usr/bin/env python3
"""
Kodak Smile AI Agent — entry point.

Compatible with:
  scripts/run_ai_agent.bat
  scripts/jenkins_ai_agent_stage.py

Does NOT modify Maestro YAML, Jenkins pipelines, or existing Excel reporting.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_ROOT.parent
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config_loader import load_config  # noqa: E402
from orchestrator import AgentOrchestrator  # noqa: E402
from agent_utils.logging_utils import setup_logging  # noqa: E402


def run_agent(
    repo_root: Path,
    *,
    mode: str | None = None,
    device_id: str | None = None,
    maestro_cmd: str | None = None,
    full_regression: bool = True,
    modules: list[str] | None = None,
    apk_path: str | None = None,
) -> int:
    overrides = {
        "mode": mode,
        "maestro_cmd": maestro_cmd,
        "apk_path": apk_path,
    }
    if modules:
        overrides["modules_include"] = modules

    cfg = load_config(repo_root, overrides=overrides)
    if not cfg.enabled:
        print("[ai-agent] disabled — exiting without changes", flush=True)
        return 0

    log = setup_logging(cfg.repo_root / "ai-agent" / "logs")
    log.info(
        "Kodak Smile AI Agent starting mode=%s full_regression=%s",
        cfg.mode,
        full_regression,
    )

    orch = AgentOrchestrator(cfg)
    if device_id:
        # Force single device via env for ATP orchestrator preference
        import os

        os.environ["ATP_ORCH_DEVICES"] = device_id
        os.environ["ANDROID_SERIAL"] = device_id

    rc, summary = orch.run_full_regression()
    print(
        f"[ai-agent] finished rc={rc} recommendation={summary.recommendation.value} "
        f"report={cfg.report_root}",
        flush=True,
    )
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kodak Smile AI Agent — autonomous full regression orchestration"
    )
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument(
        "--mode",
        choices=["observe", "assist", "autonomous"],
        default=None,
        help="Execution mode (default: assist)",
    )
    parser.add_argument("--device", default=None, help="ADB device serial")
    parser.add_argument("--maestro-cmd", default=None, help="Maestro launcher")
    parser.add_argument(
        "--full-regression",
        action="store_true",
        default=True,
        help="Run complete discovered ATP suite (default)",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=None,
        help="Limit to module/folder (repeatable). Supports aliases like login, camera, editing.",
    )
    parser.add_argument("--apk", default=None, help="Optional APK path to install if missing")
    args = parser.parse_args(argv)
    return run_agent(
        Path(args.repo).resolve(),
        mode=args.mode,
        device_id=args.device,
        maestro_cmd=args.maestro_cmd,
        full_regression=bool(args.full_regression),
        modules=args.module,
        apk_path=args.apk,
    )


if __name__ == "__main__":
    raise SystemExit(main())
