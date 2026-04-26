#!/usr/bin/env python3
"""
Post-run archive: copy logs/, reports/, optional excel/, and the final Excel report into
  <repo>/archive/run_YYYYMMDD_HHMMSS/

Does not delete source trees (cleanup already ran at job start for a clean run).
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("orch.archive")


def archive_post_run_artifacts(
    repo_root: Path,
    final_excel: Path,
    *,
    also_dirs: tuple[str, ...] = ("logs", "reports", "excel", "build-summary", "maestro-report", "test-results"),
) -> Path | None:
    """
    Snapshot artifact dirs + final Excel for audit / Jenkins artifacts.
    Returns destination folder, or None if nothing was copied.
    """
    repo_root = repo_root.resolve()
    final_excel = final_excel.resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = repo_root / "archive" / f"run_{ts}"
    dest.mkdir(parents=True, exist_ok=True)

    copied = False
    for name in also_dirs:
        src = repo_root / name
        if not src.is_dir():
            continue
        target = dest / name
        try:
            shutil.copytree(src, target, dirs_exist_ok=True)
            copied = True
            logger.info("Archived directory: %s -> %s", src, target)
        except OSError as e:
            logger.warning("Could not archive %s: %s", src, e)

    if final_excel.is_file():
        try:
            out_x = dest / final_excel.name
            shutil.copy2(final_excel, out_x)
            copied = True
            logger.info("Archived Excel: %s", out_x)
        except OSError as e:
            logger.warning("Could not archive Excel %s: %s", final_excel, e)

    if not copied:
        logger.info("No artifacts to archive (empty run or paths missing)")
        try:
            dest.rmdir()
        except OSError:
            pass
        return None

    print(f"[INFO] Run archive: {dest}", flush=True)
    return dest
