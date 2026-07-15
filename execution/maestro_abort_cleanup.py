#!/usr/bin/env python3
"""
Kill leftover Maestro automation on the Windows device agent.

Jenkins "Stop" often kills python/cmd but leaves java.exe (maestro.cli.AppKt)
because children are started with CREATE_NEW_PROCESS_GROUP. Call this on:
  - SIGINT / SIGTERM / SIGBREAK / atexit inside the orchestrator
  - Jenkins post { always } on the devices agent
"""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from .maestro_startup_gate import (
    cleanup_all_host_maestro_java,
    clear_device_adb_forwards,
    get_owned_child_pids,
    terminate_process_tree,
    unregister_owned_child_pid,
)

_cleanup_lock = threading.Lock()
_cleanup_done = False
_handlers_installed = False


def _taskkill_image(image: str) -> int:
    if os.name != "nt":
        return 0
    try:
        proc = subprocess.run(
            ["taskkill", "/IM", image, "/F", "/T"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        return int(proc.returncode or 0)
    except (OSError, subprocess.TimeoutExpired):
        return 1


def _kill_cmd_wrappers_for_maestro() -> list[int]:
    """Kill leftover cmd.exe wrappers that launched run_one_flow_on_device / maestro.bat."""
    if os.name != "nt":
        return []
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" | "
        "Where-Object { "
        "  $_.CommandLine -and ("
        "    $_.CommandLine -match 'run_one_flow_on_device\\.bat' -or "
        "    $_.CommandLine -match 'maestro\\.bat' -or "
        "    $_.CommandLine -match 'maestro\\.cli\\.AppKt'"
        "  )"
        "} | ForEach-Object { [int]$_.ProcessId }"
    )
    killed: list[int] = []
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line.isdigit():
                continue
            pid = int(line)
            terminate_process_tree(pid)
            killed.append(pid)
            print(f"[ATP] abort_cleanup cmd_wrapper_killed pid={pid}", flush=True)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return killed


def _clear_forwards_from_detected_devices(repo: Path | None) -> None:
    if repo is None:
        return
    det = repo / "detected_devices.txt"
    if not det.is_file():
        return
    try:
        lines = det.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for raw in lines:
        serial = raw.strip()
        if not serial or serial.startswith("#"):
            continue
        ok, detail = clear_device_adb_forwards(serial)
        print(
            f"[ATP] abort_cleanup adb_forward_remove device={serial} ok={ok} detail={detail!r}",
            flush=True,
        )


def abort_cleanup_maestro(*, reason: str = "abort", repo: Path | None = None) -> dict[str, int]:
    """
    Best-effort kill of Maestro CLI java + wrappers. Safe to call multiple times.
    Does not kill unrelated java.exe (IDE/Gradle) — only maestro.cli.AppKt.
    """
    global _cleanup_done
    with _cleanup_lock:
        if _cleanup_done:
            return {"skipped": 1}
        _cleanup_done = True

    print(f"[ATP] abort_cleanup begin reason={reason}", flush=True)
    owned = get_owned_child_pids()
    owned_killed = 0
    for pid in sorted(owned):
        print(f"[ATP] abort_cleanup owned_child_kill pid={pid}", flush=True)
        terminate_process_tree(pid)
        unregister_owned_child_pid(pid)
        owned_killed += 1

    java_killed = cleanup_all_host_maestro_java(keep_pids=set())
    cmd_killed = _kill_cmd_wrappers_for_maestro()
    # Second pass in case wrappers respawned java briefly.
    java_killed2 = cleanup_all_host_maestro_java(keep_pids=set())
    maestro_exe_rc = _taskkill_image("maestro.exe")
    _clear_forwards_from_detected_devices(repo)

    summary = {
        "owned_killed": owned_killed,
        "java_killed": len(java_killed) + len(java_killed2),
        "cmd_wrappers_killed": len(cmd_killed),
        "maestro_exe_taskkill_rc": maestro_exe_rc,
    }
    print(f"[ATP] abort_cleanup end {summary}", flush=True)
    return summary


def install_abort_cleanup_handlers(*, repo: Path | None = None) -> None:
    """Register atexit + signal handlers so Stop/Ctrl+C kills Maestro children."""
    global _handlers_installed
    if _handlers_installed:
        return
    _handlers_installed = True
    repo_path = Path(repo).resolve() if repo is not None else None

    def _run(reason: str) -> None:
        try:
            abort_cleanup_maestro(reason=reason, repo=repo_path)
        except Exception as exc:  # noqa: BLE001 — never fail process exit on cleanup
            print(f"[ATP] abort_cleanup_error reason={reason} err={exc!s}", flush=True)

    atexit.register(lambda: _run("atexit"))

    def _signal_handler(signum: int, _frame: object) -> None:
        _run(f"signal_{signum}")
        # Re-raise default so Jenkins sees non-zero / interrupt.
        try:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        except OSError:
            raise SystemExit(130) from None

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            pass
    print("[ATP] abort_cleanup_handlers_installed=1", flush=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    reason = "cli"
    repo: Path | None = None
    if argv:
        reason = argv[0]
    if len(argv) > 1:
        repo = Path(argv[1])
    elif (os.environ.get("WORKSPACE") or "").strip():
        repo = Path(os.environ["WORKSPACE"].strip())
    summary = abort_cleanup_maestro(reason=reason, repo=repo)
    return 0 if summary.get("skipped") or True else 0


if __name__ == "__main__":
    raise SystemExit(main())
