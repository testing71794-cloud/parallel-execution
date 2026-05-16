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


def resolve_maestro_app_home(maestro_launcher: Path | None = None) -> Path:
    """Maestro install root (parent of bin/); matches maestro.bat APP_HOME."""
    mh = os.environ.get("MAESTRO_HOME", "").strip().strip('"')
    if not mh and maestro_launcher is not None:
        mh = str(maestro_launcher.parent)
    if not mh:
        raise RuntimeError("MAESTRO_HOME is not set.")
    bin_dir = Path(mh).resolve()
    if bin_dir.name.lower() in ("bin", "scripts"):
        return bin_dir.parent
    return bin_dir


def resolve_maestro_java_exe() -> Path:
    for key in ("MAESTRO_JAVA_HOME", "JAVA_HOME"):
        root = os.environ.get(key, "").strip().strip('"')
        if not root:
            continue
        exe = Path(root) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if exe.is_file():
            return exe.resolve()
    found = shutil.which("java")
    if found:
        return Path(found).resolve()
    raise RuntimeError("Java 17+ not found (set MAESTRO_JAVA_HOME or JAVA_HOME).")


def build_maestro_java_cmd_prefix(
    maestro_launcher: Path | None = None,
) -> list[str]:
    """
    argv prefix to invoke Maestro CLI without maestro.bat (Gradle-style launcher).
    Example: [java.exe, -classpath, <app>/lib/*, maestro.cli.AppKt]
    """
    app_home = resolve_maestro_app_home(maestro_launcher)
    lib_glob = str((app_home / "lib" / "*").resolve())
    java_exe = resolve_maestro_java_exe()
    return [str(java_exe), "-classpath", lib_glob, "maestro.cli.AppKt"]


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


def _device_slug(device_id: str) -> str:
    slug = re.sub(r"[^\w\-.]+", "_", device_id.strip())
    return slug or "device"


def _parallel_maestro_isolation_enabled() -> bool:
    return os.environ.get("ATP_MAESTRO_PARALLEL_ISOLATION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _maestro_driver_host_port(launch_index: int) -> int | None:
    """
    Distinct Android driver host ports per parallel launch (avoids default localhost:7001 clashes).
    Set ATP_MAESTRO_DRIVER_PORTS=0 to disable; override with ATP_MAESTRO_DRIVER_PORT.
    """
    if not _parallel_maestro_isolation_enabled():
        return None
    # Default off: installed Maestro builds often lack --driver-host-port (needs newer CLI).
    if os.environ.get("ATP_MAESTRO_DRIVER_PORTS", "0").strip().lower() in ("0", "false", "no", "off"):
        return None
    explicit = (os.environ.get("ATP_MAESTRO_DRIVER_PORT") or "").strip()
    if explicit:
        try:
            return int(explicit)
        except ValueError:
            return None
    try:
        base = int((os.environ.get("ATP_MAESTRO_DRIVER_PORT_BASE") or "7010").strip())
    except ValueError:
        base = 7010
    return base + max(0, launch_index)


def _windows_popen_creationflags() -> int:
    if os.name != "nt":
        return 0
    flags = 0
    create_new_process_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create_new_process_group:
        flags |= create_new_process_group
    if create_no_window:
        flags |= create_no_window
    return flags


def _windows_child_process_snapshot(root_pid: int) -> str:
    """Best-effort list of direct child processes (cmd/java) for parallel-run diagnostics."""
    if os.name != "nt" or root_pid <= 0:
        return ""
    ps = (
        f"$pp={root_pid}; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.ParentProcessId -eq $pp } | "
        "Select-Object ProcessId, Name, ParentProcessId | "
        "Format-Table -AutoSize | Out-String -Width 4096"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        out = (proc.stdout or "").strip()
        if out:
            return out
        return (proc.stderr or "").strip()[:2000]
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"snapshot_error={e}"


def _find_maestro_java_pids(device_id: str) -> list[int]:
    """Maestro CLI java processes for this device (--device serial in command line)."""
    if os.name != "nt":
        return []
    dev = device_id.replace("'", "''")
    ps = (
        f"$d='{dev}'; "
        "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
        "Where-Object { $_.CommandLine -and ($_.CommandLine -match 'maestro\\.cli\\.AppKt') "
        "-and ($_.CommandLine -match [regex]::Escape($d)) } | "
        "ForEach-Object { [int]$_.ProcessId }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        pids: list[int] = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        return pids
    except (OSError, subprocess.TimeoutExpired):
        return []


def _log_maestro_process_tree(device_id: str, cmd_pid: int) -> None:
    """Poll until Maestro java PID is visible; log pid= for console checks (unique per device)."""
    java_pid: int | None = None
    for _ in range(20):
        found = _find_maestro_java_pids(device_id)
        if found:
            java_pid = found[0]
            break
        time.sleep(1.0)
    if java_pid is not None:
        print(
            f"[ATP] maestro_subprocess_launch device={device_id} pid={java_pid} "
            f"maestro_java_pid={java_pid} cmd_child_pid={cmd_pid}",
            flush=True,
        )
    else:
        print(
            f"[ATP] maestro_subprocess_launch device={device_id} pid={cmd_pid} "
            f"(maestro_java_pid=pending) cmd_child_pid={cmd_pid}",
            flush=True,
        )
    snap = _windows_child_process_snapshot(cmd_pid)
    if snap:
        print(
            f"[ATP] maestro_subprocess_tree device={device_id} cmd_pid={cmd_pid}\n{snap}",
            flush=True,
        )


def _apply_parallel_maestro_env(
    env: dict[str, str],
    *,
    repo: Path,
    suite_id: str,
    flow_path: Path,
    device_id: str,
    launch_index: int,
) -> dict[str, str | int | None]:
    """Per-device subprocess env so parallel Maestro runs do not share driver port / temp / adb serial."""
    meta: dict[str, str | int | None] = {
        "driver_port": None,
        "debug_output": None,
        "workspace": None,
        "maestro_user_home": None,
    }
    if not _parallel_maestro_isolation_enabled():
        return meta

    slug = _device_slug(device_id)
    ws = (repo / ".maestro-workspace" / slug).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    env["TMP"] = str(ws)
    env["TEMP"] = str(ws)
    meta["workspace"] = str(ws)

    tmp_dir = (repo / ".maestro_tmp" / slug).resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    env["MAESTRO_TMP_DIR"] = str(tmp_dir)

    runtime_home = (repo / ".maestro-runtime" / slug).resolve()
    runtime_home.mkdir(parents=True, exist_ok=True)
    local_app = runtime_home / "AppData" / "Local"
    roaming = runtime_home / "AppData" / "Roaming"
    local_app.mkdir(parents=True, exist_ok=True)
    roaming.mkdir(parents=True, exist_ok=True)
    env["MAESTRO_CLI_DIR"] = str(runtime_home)
    env["ATP_MAESTRO_RUNTIME_ROOT"] = str(runtime_home)
    env["LOCALAPPDATA"] = str(local_app)
    env["APPDATA"] = str(roaming)
    # Do not override USERPROFILE (breaks Windows AppDirs / Maestro init). Redirect JVM user.home.
    opts = (env.get("MAESTRO_OPTS") or "").strip()
    user_home_flag = f'-Duser.home={runtime_home}'
    env["MAESTRO_OPTS"] = f"{opts} {user_home_flag}".strip() if opts else user_home_flag
    env["ATP_MAESTRO_JAVA_DIRECT"] = "1"
    meta["maestro_user_home"] = str(runtime_home)

    env["ANDROID_SERIAL"] = device_id
    env.pop("ANDROID_DEBUG_SERIAL", None)

    port = _maestro_driver_host_port(launch_index)
    if port is not None:
        env["ATP_MAESTRO_DRIVER_PORT"] = str(port)
        meta["driver_port"] = port

    debug_root = (repo / "reports" / suite_id / "maestro-debug").resolve()
    debug_dir = debug_root / f"{flow_path.stem}__{slug}"
    debug_dir.mkdir(parents=True, exist_ok=True)
    env["ATP_MAESTRO_DEBUG_OUTPUT"] = str(debug_dir)
    meta["debug_output"] = str(debug_dir)
    return meta


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
    launch_index: int = 0,
) -> int:
    """
    Blocking invocation of scripts/run_one_flow_on_device.bat (preserves reports/status/csv layout).
    """
    bat = (repo / "scripts" / "run_one_flow_on_device.bat").resolve()
    if not bat.is_file():
        raise FileNotFoundError(bat)
    env = os.environ.copy()
    iso = _apply_parallel_maestro_env(
        env,
        repo=repo,
        suite_id=suite_id,
        flow_path=flow_path,
        device_id=device_id,
        launch_index=launch_index,
    )
    # Ensure child cmd sees the same Maestro/Java discovery as Jenkins (set_maestro_java.bat still runs inside bat).
    timeout_sec = int(os.environ.get("ATP_FLOW_TIMEOUT_SEC", str(4 * 3600)))

    # cmd /d /c <bat> (no "call") — one cmd.exe child per device; bat invokes Maestro without "call".
    cmd: list[str] = [
        "cmd.exe",
        "/d",
        "/c",
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
        "subprocess Popen run_one_flow_on_device.bat",
        device=device_id,
        flow=flow_path.name,
        parent_pid=os.getpid(),
        driver_port=iso.get("driver_port"),
        maestro_debug=iso.get("debug_output"),
    )
    print(
        f"[ATP] maestro_subprocess_launch device={device_id} flow={flow_path.stem} "
        f"ts={time.time():.3f} orchestrator_parent_pid={os.getpid()} launch_index={launch_index} "
        f"driver_port={iso.get('driver_port')} workspace={iso.get('workspace')} "
        f"maestro_user_home={iso.get('maestro_user_home')} java_direct=1",
        flush=True,
    )
    popen_kw: dict[str, Any] = {
        "cwd": str(repo.resolve()),
        "env": env,
        "stdin": subprocess.DEVNULL,
    }
    win_flags = _windows_popen_creationflags()
    if win_flags:
        popen_kw["creationflags"] = win_flags
    tree_thread: threading.Thread | None = None
    try:
        child = subprocess.Popen(cmd, **popen_kw)
        print(
            f"[ATP] maestro_subprocess_child device={device_id} flow={flow_path.stem} "
            f"cmd_child_pid={child.pid}",
            flush=True,
        )
        if os.environ.get("ATP_MAESTRO_LOG_PROCESS_TREE", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        ):
            tree_thread = threading.Thread(
                target=_log_maestro_process_tree,
                args=(device_id, child.pid),
                name=f"maestro-tree-{device_id}",
                daemon=True,
            )
            tree_thread.start()
        try:
            child.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=30)
            log_lifecycle(
                repo, suite_id, WorkerState.FAILED, "flow timeout", device=device_id, flow=flow_path.name
            )
            return 124
        code = int(child.returncode or 0)
    except OSError as e:
        log_lifecycle(
            repo,
            suite_id,
            WorkerState.FAILED,
            "run_one_flow_on_device.bat launch failed",
            device=device_id,
            flow=flow_path.name,
            error=str(e),
        )
        return 1
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
