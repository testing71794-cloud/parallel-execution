#!/usr/bin/env python3
"""Ensure Maestro driver APKs can install on each device before ATP scheduling.

Android can exhaust per-boot UID slots after many install/uninstall cycles. That
surfaces as INSTALL_FAILED_INSUFFICIENT_STORAGE / "could not be assigned a valid UID"
even when /data has free space. A reboot clears the limit.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from utils.device_utils import get_device_display_name

from .subprocess_launch import adb_argv, ensure_adb_server_port_env


def _dev_log(device_id: str) -> str:
    return get_device_display_name(device_id)


@dataclass(frozen=True)
class DeviceMaestroCheck:
    device_id: str
    ready: bool
    detail: str
    rebooted: bool = False


_UID_MARKERS = (
    "could not be assigned a valid uid",
    "install_failed_insufficient_storage",
)


def _env_flag(name: str, default: str = "1") -> bool:
    return (os.environ.get(name) or default).strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def resolve_maestro_client_jar(maestro_launcher: Path | None = None) -> Path | None:
    """Locate maestro-client.jar from launcher / MAESTRO_HOME / parallel home."""
    candidates: list[Path] = []
    if maestro_launcher is not None:
        # .../maestro/bin/maestro.bat -> .../maestro/lib
        bin_dir = maestro_launcher.resolve().parent
        candidates.append(bin_dir.parent / "lib" / "maestro-client.jar")
        # .../bin pointing at nested maestro/bin
        candidates.append(bin_dir.parent / "maestro" / "lib" / "maestro-client.jar")
    for env_key in ("MAESTRO_HOME", "ATP_MAESTRO_PARALLEL_HOME"):
        raw = (os.environ.get(env_key) or "").strip().strip('"')
        if not raw:
            continue
        p = Path(raw)
        candidates.append(p.parent / "lib" / "maestro-client.jar")
        candidates.append(p / "lib" / "maestro-client.jar")
        candidates.append(p / "maestro" / "lib" / "maestro-client.jar")
        candidates.append(p.parent / "maestro" / "lib" / "maestro-client.jar")
    for c in candidates:
        if c.is_file():
            return c.resolve()
    return None


def extract_maestro_driver_apks(jar: Path, dest_dir: Path) -> tuple[Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    app_apk = dest_dir / "maestro-app.apk"
    server_apk = dest_dir / "maestro-server.apk"
    with zipfile.ZipFile(jar, "r") as zf:
        for name, out in (
            ("maestro-app.apk", app_apk),
            ("maestro-server.apk", server_apk),
        ):
            with zf.open(name) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return app_apk, server_apk


def _adb_run(*args: str, timeout: float = 60) -> tuple[int, str]:
    cmd = adb_argv(*args)
    if not cmd:
        return 1, "adb_not_found"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def _looks_like_uid_exhaustion(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _UID_MARKERS)


def install_maestro_driver_apks(device_id: str, app_apk: Path, server_apk: Path) -> tuple[bool, str]:
    """Install both Maestro driver APKs. Returns (ok, detail)."""
    details: list[str] = []
    for label, apk in (("server", server_apk), ("app", app_apk)):
        rc, out = _adb_run(
            "-s",
            device_id,
            "install",
            "-r",
            "-g",
            str(apk),
            timeout=120,
        )
        details.append(f"{label}:rc={rc}:{out[:300]}")
        if rc != 0 or "failure" in out.lower():
            return False, " | ".join(details)
    return True, " | ".join(details)


def wait_for_device_boot(device_id: str, timeout_sec: float = 180.0) -> bool:
    """Wait until device is online and sys.boot_completed=1."""
    deadline = time.monotonic() + max(30.0, timeout_sec)
    while time.monotonic() < deadline:
        rc, state = _adb_run("-s", device_id, "get-state", timeout=15)
        if rc == 0 and (state or "").strip() == "device":
            brc, boot = _adb_run(
                "-s",
                device_id,
                "shell",
                "getprop",
                "sys.boot_completed",
                timeout=15,
            )
            if brc == 0 and (boot or "").strip() == "1":
                return True
        time.sleep(5)
    return False


def reboot_device(device_id: str, *, boot_timeout_sec: float = 180.0) -> bool:
    print(f"[ATP] device_maestro_preflight reboot device={_dev_log(device_id)}", flush=True)
    rc, out = _adb_run("-s", device_id, "reboot", timeout=30)
    if rc != 0 and "error" in (out or "").lower():
        print(
            f"[ATP] device_maestro_preflight reboot_failed device={_dev_log(device_id)} "
            f"detail={out!r}",
            flush=True,
        )
        return False
    # Give USB stack a moment before polling.
    time.sleep(8)
    ok = wait_for_device_boot(device_id, timeout_sec=boot_timeout_sec)
    print(
        f"[ATP] device_maestro_preflight reboot_wait device={_dev_log(device_id)} "
        f"ready={str(ok).lower()}",
        flush=True,
    )
    return ok


def ensure_device_maestro_ready(
    device_id: str,
    *,
    app_apk: Path,
    server_apk: Path,
    allow_reboot: bool = True,
) -> DeviceMaestroCheck:
    """Install Maestro drivers; reboot once on UID exhaustion if enabled."""
    ok, detail = install_maestro_driver_apks(device_id, app_apk, server_apk)
    if ok:
        return DeviceMaestroCheck(device_id=device_id, ready=True, detail=detail, rebooted=False)
    if allow_reboot and _looks_like_uid_exhaustion(detail):
        print(
            f"[ATP] device_maestro_preflight uid_exhaustion device={_dev_log(device_id)} "
            f"— rebooting once then retry",
            flush=True,
        )
        if reboot_device(device_id):
            ok2, detail2 = install_maestro_driver_apks(device_id, app_apk, server_apk)
            if ok2:
                return DeviceMaestroCheck(
                    device_id=device_id,
                    ready=True,
                    detail=f"rebooted_ok; {detail2}",
                    rebooted=True,
                )
            return DeviceMaestroCheck(
                device_id=device_id,
                ready=False,
                detail=f"after_reboot_still_fail; first={detail}; retry={detail2}",
                rebooted=True,
            )
        return DeviceMaestroCheck(
            device_id=device_id,
            ready=False,
            detail=f"reboot_failed; {detail}",
            rebooted=False,
        )
    return DeviceMaestroCheck(device_id=device_id, ready=False, detail=detail, rebooted=False)


def filter_devices_maestro_ready(
    devices: list[str],
    *,
    maestro_launcher: Path | None = None,
    repo: Path | None = None,
) -> tuple[list[str], list[DeviceMaestroCheck]]:
    """
    Return (devices_ready, devices_failed).
    Disabled when ATP_DEVICE_MAESTRO_PREFLIGHT=0.
    """
    if not _env_flag("ATP_DEVICE_MAESTRO_PREFLIGHT", "1"):
        print("[ATP] device_maestro_preflight skipped (ATP_DEVICE_MAESTRO_PREFLIGHT=0)", flush=True)
        return list(devices), []

    ensure_adb_server_port_env()
    print(
        f"[ATP] device_maestro_preflight begin device_count={len(devices)}",
        flush=True,
    )
    jar = resolve_maestro_client_jar(maestro_launcher)
    if jar is None:
        print(
            "[ATP] device_maestro_preflight WARN: maestro-client.jar not found — skip probe",
            flush=True,
        )
        return list(devices), []

    allow_reboot = _env_flag("ATP_MAESTRO_UID_REBOOT", "1")
    ready: list[str] = []
    failed: list[DeviceMaestroCheck] = []
    tmp: Path | None = None
    try:
        tmp = Path(tempfile.mkdtemp(prefix="atp_maestro_apks_"))
        app_apk, server_apk = extract_maestro_driver_apks(jar, tmp)
        print(
            f"[ATP] device_maestro_preflight apks jar={jar} "
            f"app={app_apk.name} server={server_apk.name} allow_reboot={allow_reboot}",
            flush=True,
        )
        for device_id in devices:
            check = ensure_device_maestro_ready(
                device_id,
                app_apk=app_apk,
                server_apk=server_apk,
                allow_reboot=allow_reboot,
            )
            if check.ready:
                ready.append(device_id)
                print(
                    f"[ATP] device_maestro_ok device={_dev_log(device_id)} "
                    f"rebooted={str(check.rebooted).lower()}",
                    flush=True,
                )
            else:
                failed.append(check)
                print(
                    f"[ATP] device_maestro_unusable device={_dev_log(device_id)} "
                    f"detail={check.detail!r}",
                    flush=True,
                )
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        print(f"[ATP] device_maestro_preflight WARN: {exc} — skip probe", flush=True)
        return list(devices), []
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)

    summary = {
        "ts": time.time(),
        "ready": ready,
        "failed": [
            {
                "device_id": f.device_id,
                "detail": f.detail,
                "rebooted": f.rebooted,
            }
            for f in failed
        ],
    }
    if repo is not None:
        out_dir = repo / "build-summary"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "device_maestro_preflight.json"
        try:
            path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(f"[ATP] device_maestro_preflight_summary path={path}", flush=True)
        except OSError as exc:
            print(
                f"[ATP] device_maestro_preflight_summary_write_failed error={exc}",
                flush=True,
            )

    print(
        f"[ATP] device_maestro_preflight end ready={len(ready)} failed={len(failed)} "
        f"ready_devices=[{', '.join(_dev_log(d) for d in ready)}]",
        flush=True,
    )
    if failed and ready:
        print(
            f"[ATP] device_maestro_preflight: continuing with {len(ready)} device(s); "
            f"skipped {len(failed)} maestro-unusable",
            flush=True,
        )
    return ready, failed
