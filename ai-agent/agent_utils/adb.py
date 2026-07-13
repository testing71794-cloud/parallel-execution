"""Thin ADB process helpers used by device / artifact modules."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def resolve_adb() -> str:
    try:
        # Prefer repo execution helper when available
        from execution.subprocess_launch import resolve_adb_executable

        adb = resolve_adb_executable()
        if adb:
            return adb
    except Exception:
        pass
    found = shutil.which("adb")
    if found:
        return found
    candidates = [
        Path.home() / "AppData" / "Local" / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        Path(r"C:\Android\platform-tools\adb.exe"),
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return "adb"


def adb_run(
    args: list[str],
    *,
    device: str | None = None,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    cmd = [resolve_adb()]
    if device:
        cmd.extend(["-s", device])
    cmd.extend(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
