#!/usr/bin/env python3
"""
Blocking Maestro / ATP process helpers (Linux-first API, Windows-compatible).

- No detached shells: callers use subprocess.run(..., stdin=DEVNULL) with timeouts.
- Structured lifecycle lines (separate from per-flow Maestro logs under reports/).
- Conservative pre-run hygiene (adb start-server; optional forward snapshot; optional orphan kill via env).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .flow_timing import append_timing, read_status_fields

_lifecycle_log_lock = threading.Lock()


class WorkerState:
    IDLE = "IDLE"
    ALLOCATED = "ALLOCATED"
    PREPARING = "PREPARING"
    CLEANUP = "CLEANUP"
    ADB_READY = "ADB_READY"
    MAESTRO_STARTING = "MAESTRO_STARTING"
    DRIVER_CONNECTED = "DRIVER_CONNECTED"
    RUNNING = "RUNNING"
    REPORTING = "REPORTING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def lifecycle_path(repo: Path, suite_id: str) -> Path:
    p = repo / "reports" / suite_id / "orchestrator_lifecycle.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_lifecycle(repo: Path, suite_id: str, state: str, message: str, **fields: Any) -> None:
    """Append one JSON line; does not alter Maestro per-flow logs."""
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "state": state,
        "msg": message,
        **fields,
    }
    lp = lifecycle_path(repo, suite_id)
    line = json.dumps(rec, ensure_ascii=False) + "\n"
    with _lifecycle_log_lock:
        with lp.open("a", encoding="utf-8", errors="replace") as f:
            f.write(line)


def _adb_exe() -> str | None:
    for env in ("ADB_HOME",):
        root = os.environ.get(env, "").strip().strip('"')
        if root:
            exe = Path(root) / ("adb.exe" if os.name == "nt" else "adb")
            if exe.is_file():
                return str(exe)
    for root_env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if root:
            exe = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if exe.is_file():
                return str(exe)
    w = shutil.which("adb")
    return w


def adb_start_server(suite_id: str, repo: Path) -> None:
    exe = _adb_exe()
    if not exe:
        log_lifecycle(repo, suite_id, WorkerState.ADB_READY, "adb not on PATH; skip start-server")
        return
    try:
        subprocess.run([exe, "start-server"], capture_output=True, text=True, timeout=90, check=False)
        log_lifecycle(repo, suite_id, WorkerState.ADB_READY, "adb start-server", adb=exe)
    except (OSError, subprocess.TimeoutExpired) as e:
        log_lifecycle(repo, suite_id, WorkerState.FAILED, "adb start-server failed", error=str(e))


def snapshot_adb_forwards(suite_id: str, repo: Path) -> None:
    exe = _adb_exe()
    if not exe:
        return
    try:
        proc = subprocess.run([exe, "forward", "--list"], capture_output=True, text=True, timeout=30, check=False)
        tail = ((proc.stdout or "") + (proc.stderr or ""))[:4000]
        log_lifecycle(repo, suite_id, WorkerState.CLEANUP, "adb forward --list snapshot", snapshot=tail)
    except (OSError, subprocess.TimeoutExpired) as e:
        log_lifecycle(repo, suite_id, WorkerState.CLEANUP, "adb forward list failed", error=str(e))


def pre_maestro_cleanup(
    device_id: str,
    suite_id: str,
    repo: Path,
    *,
    allow_maestro_kill: bool | None = None,
) -> None:
    log_lifecycle(repo, suite_id, WorkerState.CLEANUP, "pre_maestro_cleanup begin", device=device_id)
    adb_start_server(suite_id, repo)
    if _truthy("ATP_ORCH_SNAPSHOT_ADB_FORWARDS"):
        snapshot_adb_forwards(suite_id, repo)
    # When None, preserve legacy behavior (kill allowed). Orchestrator passes False for multi-device waves.
    if allow_maestro_kill is None:
        allow_maestro_kill = True
    if _truthy("ATP_ORCH_KILL_MAESTRO_ORPHANS") and allow_maestro_kill and os.name == "nt":
        try:
            proc = subprocess.run(
                ["taskkill", "/IM", "maestro.exe", "/F", "/T"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            log_lifecycle(
                repo,
                suite_id,
                WorkerState.CLEANUP,
                "taskkill maestro.exe (ATP_ORCH_KILL_MAESTRO_ORPHANS=1)",
                rc=proc.returncode,
                out=(proc.stdout or "")[:2000],
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            log_lifecycle(repo, suite_id, WorkerState.CLEANUP, "taskkill maestro.exe failed", error=str(e))


def resolve_maestro_launcher(maestro_cmd: str) -> Path:
    """Match run_atp_testcase_flows.ps1 Resolve-MaestroLauncherPath (MAESTRO_HOME)."""
    raw = (maestro_cmd or "").strip().strip('"')
    if raw:
        p = Path(raw)
        if p.is_file():
            return p.resolve()
    mh = os.environ.get("MAESTRO_HOME", "").strip().strip('"')
    if not mh:
        raise RuntimeError("MAESTRO_HOME is not set and maestro_cmd is not a valid file path.")
    base = Path(mh)
    for name in ("maestro.bat", "maestro.cmd"):
        cand = base / name
        if cand.is_file():
            return cand.resolve()
    raise RuntimeError(f"maestro.bat / maestro.cmd not found under MAESTRO_HOME: {mh}")


def flow_log_tail(repo: Path, suite_id: str, flow_path: Path, device_id: str) -> str:
    """Same stem convention as scripts/run_one_flow_on_device.bat SAFE_FLOW."""
    flow_name = re.sub(r"\s+", "_", flow_path.stem)
    safe_dev = re.sub(r"\s+", "_", device_id)
    logf = repo / "reports" / suite_id / "logs" / f"{flow_name}_{safe_dev}.log"
    if not logf.is_file():
        return ""
    try:
        lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-120:])
    except OSError:
        return ""


def post_run_validate(
    repo: Path,
    suite_id: str,
    exit_code: int,
    flow_path: Path,
    device_id: str,
) -> None:
    """Best-effort log signals; does not override exit_code semantics."""
    tail = flow_log_tail(repo, suite_id, flow_path, device_id)
    if exit_code == 0:
        if "7001" in tail and "Connection refused" in tail:
            log_lifecycle(
                repo,
                suite_id,
                WorkerState.RECOVERING,
                "anomaly: exit 0 but log mentions localhost:7001 refused",
                flow=flow_path.name,
                device=device_id,
            )
        elif "Starting Maestro test" in tail or "Starting Maestro test (flow1b)" in tail:
            log_lifecycle(
                repo,
                suite_id,
                WorkerState.DRIVER_CONNECTED,
                "maestro driver session appeared to start (log heuristic)",
                flow=flow_path.name,
                device=device_id,
            )
        return
    if "7001" in tail and "Connection refused" in tail:
        log_lifecycle(
            repo,
            suite_id,
            WorkerState.RECOVERING,
            "localhost:7001 connection refused in log (driver IPC)",
            flow=flow_path.name,
            device=device_id,
        )


def run_run_one_flow_device_bat(
    *,
    repo: Path,
    suite_id: str,
    flow_path: Path,
    device_id: str,
    app_id: str,
    clear_state: str,
    maestro_launcher: Path,
    include_tag: str = "__EMPTY__",
) -> int:
    """
    Blocking invocation of scripts/run_one_flow_on_device.bat (preserves reports/status/csv layout).
    """
    bat = (repo / "scripts" / "run_one_flow_on_device.bat").resolve()
    if not bat.is_file():
        raise FileNotFoundError(bat)
    env = os.environ.copy()
    # Ensure child cmd sees the same Maestro/Java discovery as Jenkins (set_maestro_java.bat still runs inside bat).
    timeout_sec = int(os.environ.get("ATP_FLOW_TIMEOUT_SEC", str(4 * 3600)))

    cmd: list[str] = [
        "cmd.exe",
        "/c",
        "call",
        str(bat),
        suite_id,
        str(flow_path.resolve()),
        device_id,
        app_id,
        clear_state,
        str(maestro_launcher),
        include_tag,
    ]
    log_lifecycle(
        repo,
        suite_id,
        WorkerState.MAESTRO_STARTING,
        "subprocess.run run_one_flow_on_device.bat",
        device=device_id,
        flow=flow_path.name,
        pid=os.getpid(),
    )
    print(
        f"[ATP] maestro_subprocess_launch device={device_id} flow={flow_path.stem} "
        f"ts={time.time():.3f} pid={os.getpid()}",
        flush=True,
    )
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo.resolve()),
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=timeout_sec,
            check=False,
        )
        code = int(proc.returncode)
    except subprocess.TimeoutExpired:
        log_lifecycle(repo, suite_id, WorkerState.FAILED, "flow timeout", device=device_id, flow=flow_path.name)
        return 124
    log_lifecycle(
        repo,
        suite_id,
        WorkerState.REPORTING if code == 0 else WorkerState.FAILED,
        "run_one_flow_on_device.bat finished",
        device=device_id,
        flow=flow_path.name,
        exit_code=code,
    )
    post_run_validate(repo, suite_id, code, flow_path, device_id)
    _record_flow_timing(repo, suite_id, flow_path, device_id, code)
    return code


def _status_file_path(repo: Path, suite_id: str, flow_path: Path, device_id: str) -> Path:
    safe_flow = flow_path.stem.replace(" ", "_")
    safe_device = device_id.replace(" ", "_")
    return repo / "status" / f"{suite_id}__{safe_flow}__{safe_device}.txt"


def _record_flow_timing(
    repo: Path, suite_id: str, flow_path: Path, device_id: str, exit_code: int
) -> None:
    if os.environ.get("ATP_FLOW_TIMING", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    st_path = _status_file_path(repo, suite_id, flow_path, device_id)
    fields = read_status_fields(st_path)
    dur_s = fields.get("duration_ms", "").strip()
    try:
        duration_ms = int(dur_s) if dur_s else 0
    except ValueError:
        duration_ms = 0
    append_timing(
        repo,
        suite_id,
        flow=flow_path.stem,
        device=device_id,
        duration_ms=duration_ms,
        status=fields.get("status", "UNKNOWN"),
        exit_code=exit_code,
        reason=fields.get("reason", ""),
        extra={
            "maestro_device_reconnect_retry": fields.get("maestro_device_reconnect_retry", ""),
            "maestro_driver_7001_retry": fields.get("maestro_driver_7001_retry", ""),
        },
    )
    if duration_ms > 0:
        log_lifecycle(
            repo,
            suite_id,
            WorkerState.REPORTING,
            "flow timing recorded",
            device=device_id,
            flow=flow_path.name,
            duration_ms=duration_ms,
        )
