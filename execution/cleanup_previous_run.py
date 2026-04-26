#!/usr/bin/env python3
"""
Remove artifacts from prior runs so Excel and logs only reflect the current execution.

Deletes:
  - <repo>/logs/  (orchestrator + per-device Maestro logs/JUnit from this runner)
  - <repo>/build-summary/  (including final_execution_report.xlsx and other summary files)

Safe to run before execution/run_parallel_devices.py.
Does not modify Maestro flow YAML.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("orch.cleanup")


def cleanup_for_new_run(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    logs = repo_root / "logs"
    summary = repo_root / "build-summary"

    if logs.is_dir():
        try:
            shutil.rmtree(logs, ignore_errors=False)
            logger.info("Removed logs directory: %s", logs)
        except OSError as e:
            logger.error("Could not remove logs: %s", e)
            raise

    if summary.is_dir():
        try:
            shutil.rmtree(summary, ignore_errors=False)
            logger.info("Removed build-summary directory: %s", summary)
        except OSError as e:
            logger.error("Could not remove build-summary: %s", e)
            raise

    # Explicit final report at repo root (if ever used there)
    loose = repo_root / "final_execution_report.xlsx"
    if loose.is_file():
        loose.unlink()
        logger.info("Removed %s", loose)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Clean logs and build-summary before a parallel run")
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    args = p.parse_args()
    try:
        cleanup_for_new_run(args.repo_root)
    except OSError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
