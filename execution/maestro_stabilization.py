#!/usr/bin/env python3
"""Native-parallel Maestro stabilization helpers (ADB, warmup, watchdog, stagger)."""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

_staggered_devices: set[str] = set()
_stagger_lock = threading.Lock()

from utils.device_utils import get_device_display_name

from .maestro_startup_gate import (
    _read_log_since,
    clear_device_adb_forwards,
    terminate_process_tree,
)


def _adb_exe() -> str | None:
    from .maestro_runner import _adb_exe as _fn

    return _fn()


def _dev_log(device_id: str) -> str:
    return get_device_display_name(device_id)


def parallel_device_stagger_sec(launch_index: int) -> float:
    """
    Startup-only stagger: index 0 -> 0s, index 1 -> 2s, index 2 -> 4s (default step 2s).
  Does not serialize flow execution after workers start.
    """
    if launch_index <= 0:
        return 0.0
    raw = (os.environ.get("ATP_PARALLEL_DEVICE_STAGGER_SEC") or "2").strip()
    try:
        step = max(0.0, float(raw))
    except ValueError:
        step = 2.0
    return step * launch_index


def log_startup_stagger(device_id: str, launch_index: int) -> None:
    delay = parallel_device_stagger_sec(launch_index)
    if delay <= 0:
        return
    print(
        f"[ATP] startup_stagger device={_dev_log(device_id)} delay_sec={delay:.1f}",
        flush=True,
    )
    time.sleep(delay)


def maybe_startup_stagger_once(device_id: str, launch_index: int) -> None:
    """Apply startup stagger once per device serial (first flow only)."""
    with _stagger_lock:
        if device_id in _staggered_devices:
            return
        _staggered_devices.add(device_id)
    log_startup_stagger(device_id, launch_index)


def aggressive_adb_device_cleanup(device_id: str) -> bool:
    """forward/reverse cleanup + stale UIAutomator kill before each Maestro launch."""
    print(f"[ATP] adb_cleanup_start device={_dev_log(device_id)}", flush=True)
    exe = _adb_exe()
    if not exe:
        print(
            f"[ATP] adb_cleanup_end device={_dev_log(device_id)} success=false",
            flush=True,
        )
        return False
    ok = True
    for args in (
        ["-s", device_id, "forward", "--remove-all"],
        ["-s", device_id, "reverse", "--remove-all"],
        ["-s", device_id, "shell", "pkill", "-f", "uiautomator"],
    ):
        try:
            proc = subprocess.run(
                [exe, *args],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode not in (0, 1):
                ok = False
        except (OSError, subprocess.TimeoutExpired):
            ok = False
    print(
        f"[ATP] adb_cleanup_end device={_dev_log(device_id)} success={str(ok).lower()}",
        flush=True,
    )
    return ok


def disable_device_animations(device_id: str) -> None:
    """Samsung-safe animation scale disable (best-effort)."""
    print(f"[ATP] animation_disable device={_dev_log(device_id)}", flush=True)
    exe = _adb_exe()
    if not exe:
        return
    for key in (
        "window_animation_scale",
        "transition_animation_scale",
        "animator_duration_scale",
    ):
        try:
            subprocess.run(
                [exe, "-s", device_id, "shell", "settings", "put", "global", key, "0"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def log_isolated_runtime_confirmed(
    *,
    device_id: str,
    meta: dict[str, Any],
) -> None:
    if not meta.get("maestro_user_home"):
        return
    print("[ATP] isolated_runtime_confirmed", flush=True)
    print(f"device={_dev_log(device_id)}", flush=True)
    print(f"user_home={meta.get('maestro_user_home')}", flush=True)
    print(f"workspace={meta.get('workspace')}", flush=True)
    print(f"localappdata={meta.get('localappdata')}", flush=True)
    print(f"debug_output={meta.get('debug_output')}", flush=True)


def _maestro_warmup_cmd(
    maestro_launcher: Path,
    device_id: str,
    subcommand: str,
    env: dict[str, str],
) -> list[str]:
    if env.get("ATP_MAESTRO_JAVA_DIRECT", "").strip() == "1":
        try:
            from .maestro_runner import build_maestro_java_cmd_prefix

            prefix = build_maestro_java_cmd_prefix(
                maestro_launcher,
                user_home=env.get("ATP_JAVA_USER_HOME"),
            )
            return [*prefix, "--device", device_id, subcommand]
        except (RuntimeError, OSError):
            pass
    return [str(maestro_launcher), "--device", device_id, subcommand]


def run_maestro_warmup(
    *,
    maestro_launcher: Path,
    device_id: str,
    env: dict[str, str],
) -> tuple[bool, float]:
    """
    Lightweight Maestro init (hierarchy preferred, status fallback).
    Failures are logged only; callers continue with the real flow.
    """
    t0 = time.monotonic()
    print(f"[ATP] maestro_warmup_start device={_dev_log(device_id)}", flush=True)
    timeout = float(os.environ.get("ATP_MAESTRO_WARMUP_TIMEOUT_SEC", "20"))
    success = False
    for subcommand in ("hierarchy", "status"):
        cmd = _maestro_warmup_cmd(maestro_launcher, device_id, subcommand, env)
        try:
            proc = subprocess.run(
                cmd,
                cwd=env.get("ATP_REPO_ROOT") or None,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode == 0:
                success = True
                break
        except subprocess.TimeoutExpired:
            pass
        except OSError:
            pass
    duration = time.monotonic() - t0
    print(
        f"[ATP] maestro_warmup_end device={_dev_log(device_id)} "
        f"success={str(success).lower()} duration_sec={duration:.1f}",
        flush=True,
    )
    if not success:
        print(
            f"[ATP] maestro_warmup_warn device={_dev_log(device_id)} "
            f"continuing_with_flow=true",
            flush=True,
        )
    return success, duration


def startup_watchdog_timeout_sec() -> float:
    raw = (os.environ.get("ATP_MAESTRO_STARTUP_WATCHDOG_SEC") or "45").strip()
    try:
        return max(10.0, float(raw))
    except ValueError:
        return 45.0


def startup_watchdog_enabled(*, native_parallel: bool, use_startup_gate: bool) -> bool:
    if not native_parallel or use_startup_gate:
        return False
    raw = (os.environ.get("ATP_MAESTRO_STARTUP_WATCHDOG") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def wait_for_maestro_log_activity(
    *,
    log_path: Path,
    log_start_offset: int,
    timeout_sec: float | None = None,
) -> bool:
    """True when the per-flow log grows or contains non-whitespace after launch."""
    timeout = timeout_sec if timeout_sec is not None else startup_watchdog_timeout_sec()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if log_path.is_file() and log_path.stat().st_size > log_start_offset:
                chunk = _read_log_since(log_path, log_start_offset, max_bytes=4096)
                if chunk.strip():
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def handle_startup_watchdog_failure(
    *,
    device_id: str,
    child_pid: int | None,
    driver_port: int | None,
    repo: Path,
    suite_id: str,
) -> None:
    print(f"[ATP] startup_watchdog_triggered device={_dev_log(device_id)}", flush=True)
    if child_pid:
        terminate_process_tree(child_pid)
    clear_device_adb_forwards(device_id)
    try:
        exe = _adb_exe()
        if exe:
            subprocess.run(
                [exe, "-s", device_id, "reverse", "--remove-all"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if driver_port:
        from .maestro_startup_gate import wait_for_host_port_free  # noqa: PLC0415

        wait_for_host_port_free(driver_port, timeout_sec=15.0)
