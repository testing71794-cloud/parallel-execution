#!/usr/bin/env python3
"""
Auto-cleanup before each orchestrated run so logs, JUnit, and Excel never leak
from previous executions. Missing paths are ignored (no failure).

Deletes (under repo root when present):
  logs/, build-summary/, test-results/, maestro-report/, reports/
  final_execution_report.xlsx (repo root)

Also prints: CLEANUP COMPLETED
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("orch.cleanup")

FOLDERS = (
    "logs",
    "build-summary",
    "test-results",
    "maestro-report",
    "reports",
)

FILES = (
    "final_execution_report.xlsx",
)


def cleanup_for_new_run(repo_root: Path) -> None:
    repo_root = repo_root.resolve()

    for name in FOLDERS:
        path = repo_root / name
        if not path.exists():
            continue
        if not path.is_dir():
            logger.warning("Skip cleanup (not a directory): %s", path)
            continue
        try:
            shutil.rmtree(path, ignore_errors=False)
            logger.info("Removed directory: %s", path)
        except OSError as e:
            logger.warning("Could not remove directory %s: %s — continuing", path, e)

    for name in FILES:
        path = repo_root / name
        if not path.is_file():
            continue
        try:
            path.unlink()
            logger.info("Removed file: %s", path)
        except OSError as e:
            logger.warning("Could not remove file %s: %s — continuing", path, e)

    logger.info("Cleanup completed")
    print("[INFO] Cleanup completed", flush=True)
    print("CLEANUP COMPLETED", flush=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    p = argparse.ArgumentParser(description="Remove prior run artifacts (safe if paths missing)")
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root",
    )
    args = p.parse_args()
    cleanup_for_new_run(args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
