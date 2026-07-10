#!/usr/bin/env python3
"""Verify target app package is installed per device before ATP scheduling."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from utils.device_utils import get_device_display_name

from .subprocess_launch import resolve_adb_executable


def _dev_log(device_id: str) -> str:
    return get_device_display_name(device_id)


@dataclass(frozen=True)
class DeviceAppCheck:
    device_id: str
    installed: bool
    detail: str


def check_app_installed(device_id: str, app_id: str) -> DeviceAppCheck:
    """Run ``adb -s DEVICE shell pm path PACKAGE``."""
    app_id = (app_id or "").strip()
    if not app_id:
        return DeviceAppCheck(device_id=device_id, installed=False, detail="empty_app_id")
    adb = resolve_adb_executable()
    if not adb:
        return DeviceAppCheck(device_id=device_id, installed=False, detail="adb_not_found")
    try:
        proc = subprocess.run(
            [adb, "-s", device_id, "shell", "pm", "path", app_id],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        installed = proc.returncode == 0 and "package:" in out.lower()
        return DeviceAppCheck(
            device_id=device_id,
            installed=installed,
            detail=out[:500] if out else f"rc={proc.returncode}",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DeviceAppCheck(device_id=device_id, installed=False, detail=str(exc))


def filter_devices_with_app(
    devices: list[str],
    app_id: str,
    *,
    repo: Path | None = None,
) -> tuple[list[str], list[DeviceAppCheck]]:
    """
    Return (devices_ready, devices_missing_app).
    Does not raise; logs per-device results.
    """
    ready: list[str] = []
    missing: list[DeviceAppCheck] = []
    print(
        f"[ATP] device_app_preflight begin app_id={app_id!r} device_count={len(devices)}",
        flush=True,
    )
    for device_id in devices:
        check = check_app_installed(device_id, app_id)
        if check.installed:
            ready.append(device_id)
            print(
                f"[ATP] device_app_ok device={_dev_log(device_id)} app={app_id}",
                flush=True,
            )
        else:
            missing.append(check)
            print(
                f"[ATP] device_app_missing device={_dev_log(device_id)} app={app_id} "
                f"detail={check.detail!r}",
                flush=True,
            )
    summary = {
        "app_id": app_id,
        "ts": time.time(),
        "ready": ready,
        "missing": [
            {"device_id": m.device_id, "detail": m.detail} for m in missing
        ],
    }
    if repo is not None:
        out_dir = repo / "build-summary"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "device_app_preflight.json"
        try:
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"[ATP] device_app_preflight_summary path={path}", flush=True)
        except OSError as exc:
            print(f"[ATP] device_app_preflight_summary_write_failed error={exc}", flush=True)
    print(
        f"[ATP] device_app_preflight end ready={len(ready)} missing_app={len(missing)} "
        f"ready_devices=[{', '.join(_dev_log(d) for d in ready)}]",
        flush=True,
    )
    if missing:
        print(
            "[ATP] device_app_preflight skipped_devices="
            + ", ".join(_dev_log(m.device_id) for m in missing),
            flush=True,
        )
    return ready, missing


# Orchestrator / bat alignment: exit 23 = app not installed (treated as SKIP not suite FAIL).
EXIT_APP_NOT_INSTALLED = 23
