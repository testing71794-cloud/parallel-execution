"""Subprocess launch helpers — argv lists only; never shell=True."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence


def log_subprocess_launch(
    argv: Sequence[str],
    *,
    cwd: str | Path,
    shell: bool = False,
    label: str = "subprocess",
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Log argv, cwd, and shell mode before Popen/run (Jenkins path-with-spaces diagnostics)."""
    print(f"[ATP] {label} argv={list(argv)!r}", flush=True)
    print(f"[ATP] {label} cwd={str(cwd)!r}", flush=True)
    print(f"[ATP] {label} shell={shell}", flush=True)
    if extra:
        for key, value in extra.items():
            print(f"[ATP] {label} {key}={value!r}", flush=True)


def windows_cmd_bat_argv(bat: Path, *args: str) -> list[str]:
    """
    argv for ``subprocess.run(..., shell=False)`` to execute a Windows ``.bat``.

    On Windows, CreateProcess can launch ``.bat`` files directly when the .bat path
    is argv[0] and each argument is a separate list element. **Do not** wrap with
    ``cmd.exe /c`` and multiple tokens — that splits paths at spaces
    (``'C:\\...\\Kodak' is not recognized``).
    """
    return [str(bat.resolve()), *args]


def resolve_adb_executable() -> str | None:
    """Resolved adb.exe path for argv-list subprocess (never bare ``adb`` on Windows)."""
    for env in ("ADB_HOME",):
        root = os.environ.get(env, "").strip().strip('"')
        if root:
            exe = Path(root) / ("adb.exe" if os.name == "nt" else "adb")
            if exe.is_file():
                return str(exe.resolve())
    for root_env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if root:
            exe = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if exe.is_file():
                return str(exe.resolve())
    found = shutil.which("adb")
    return found
