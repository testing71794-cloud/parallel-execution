#!/usr/bin/env python3
"""
Serialize Maestro AndroidDriver session initialization across devices on one host.

Holds a global lock only until the per-flow log shows a stable session (e.g. '> Flow').
Full YAML execution continues in parallel after the lock is released.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils.device_utils import get_device_display_name  # noqa: E402


def _dev_log(device_id: str) -> str:
    return get_device_display_name(device_id)


_startup_lock = threading.Lock()
_owned_child_pids: set[int] = set()
_owned_pids_lock = threading.Lock()


def startup_gate_enabled(device_count: int = 1) -> bool:
    """
    Serialize Maestro Android driver init across devices on one host (multi-device legacy only).

    Default OFF for:
    - single-device runs (log-marker gate caused ready_timeout while Maestro was healthy)
    - native parallel (driver ports / isolated runtime)

    Override: ATP_MAESTRO_STARTUP_GATE=0|1
    """
    raw = os.environ.get("ATP_MAESTRO_STARTUP_GATE", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # Single USB device: no startup lock / log-marker gate unless explicitly forced.
    if device_count <= 1:
        return False
    try:
        from .maestro_capabilities import legacy_serialized_allowed, native_parallel_active

        if native_parallel_active(device_count):
            return False
        return legacy_serialized_allowed()
    except ImportError:
        return True


def parallel_startup_delay_sec(*, legacy_mode: bool = False, device_count: int = 1) -> float:
    if not legacy_mode:
        try:
            from .maestro_capabilities import is_native_parallel_env_active, native_parallel_active

            if is_native_parallel_env_active() or native_parallel_active(device_count):
                return 0.0
        except ImportError:
            pass
    if legacy_mode:
        raw = (os.environ.get("MAESTRO_PARALLEL_STARTUP_DELAY_SEC") or "8").strip()
    else:
        raw = (os.environ.get("MAESTRO_PARALLEL_STARTUP_DELAY_SEC") or "0").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 8.0 if legacy_mode else 0.0


def startup_ready_timeout_sec() -> float:
    raw = (os.environ.get("ATP_MAESTRO_STARTUP_READY_TIMEOUT_SEC") or "180").strip()
    try:
        return max(30.0, float(raw))
    except ValueError:
        return 180.0


def startup_max_retries() -> int:
    raw = (os.environ.get("ATP_MAESTRO_STARTUP_RETRIES") or "2").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 2


def startup_retry_backoff_sec(attempt: int) -> float:
    """Backoff before retry (attempt is 1-based retry index, >=2)."""
    try:
        base = float((os.environ.get("ATP_MAESTRO_STARTUP_RETRY_BACKOFF_SEC") or "3").strip())
    except ValueError:
        base = 3.0
    return min(base * max(1, attempt - 1), 20.0)


def planned_driver_port(launch_index: int) -> int:
    """Deterministic host port plan (7001 + index). Passed to Maestro global --driver-host-port."""
    try:
        base = int((os.environ.get("ATP_MAESTRO_DRIVER_PORT_BASE") or "7001").strip())
    except ValueError:
        base = 7001
    return base + max(0, launch_index)


def register_owned_child_pid(pid: int) -> None:
    if pid > 0:
        with _owned_pids_lock:
            _owned_child_pids.add(pid)


def unregister_owned_child_pid(pid: int) -> None:
    with _owned_pids_lock:
        _owned_child_pids.discard(pid)


def is_owned_child_pid(pid: int) -> bool:
    with _owned_pids_lock:
        return pid in _owned_child_pids


def get_owned_child_pids() -> set[int]:
    """Snapshot of Maestro child PIDs registered by this orchestrator process."""
    with _owned_pids_lock:
        return set(_owned_child_pids)


def _kill_all_host_java_enabled() -> bool:
    """Host-wide java kill is opt-in only (breaks concurrent device workers)."""
    return os.environ.get("ATP_MAESTRO_KILL_ALL_JAVA", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _adb_exe() -> str | None:
    import shutil

    for root_env in ("ADB_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if not root:
            continue
        if root_env == "ADB_HOME":
            exe = Path(root) / ("adb.exe" if os.name == "nt" else "adb")
        else:
            exe = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if exe.is_file():
            return str(exe)
    found = shutil.which("adb")
    return found


def list_adb_forwards(*, device_id: str | None = None) -> str:
    exe = _adb_exe()
    if not exe:
        return ""
    cmd = [exe, "forward", "--list"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        text = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if device_id:
            lines = [ln for ln in text.splitlines() if device_id in ln]
            return "\n".join(lines) if lines else "(none for device)"
        return text or "(empty)"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(error: {e})"


def log_adb_forwards(device_id: str, phase: str) -> None:
    listing = list_adb_forwards(device_id=device_id)
    global_list = list_adb_forwards()
    print(
        f"[ATP] adb_forward_list phase={phase} device={_dev_log(device_id)}\n"
        f"  device_forwards={listing!r}\n"
        f"  all_forwards={global_list[:2000]!r}",
        flush=True,
    )


def clear_device_adb_forwards(device_id: str) -> tuple[bool, str]:
    exe = _adb_exe()
    if not exe:
        return False, "adb_not_found"
    try:
        proc = subprocess.run(
            [exe, "-s", device_id, "forward", "--remove-all"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        detail = ((proc.stdout or "") + (proc.stderr or "")).strip()[:500]
        ok = proc.returncode == 0
        return ok, detail or f"rc={proc.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def wait_for_host_port_free(port: int, *, timeout_sec: float | None = None) -> bool:
    """Wait until localhost:port is not LISTENING (Windows netstat)."""
    if port <= 0:
        return True
    timeout = timeout_sec if timeout_sec is not None else float(
        os.environ.get("ATP_MAESTRO_PORT_FREE_WAIT_SEC", "45")
    )
    deadline = time.monotonic() + timeout
    port_token = f":{port}"
    while time.monotonic() < deadline:
        if os.name == "nt":
            try:
                proc = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                busy = False
                for line in (proc.stdout or "").splitlines():
                    if port_token in line and "LISTENING" in line.upper():
                        busy = True
                        break
                if not busy:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                return True
        else:
            return True
        time.sleep(1.0)
    return False


def _find_maestro_java_pids_for_device(device_id: str) -> list[int]:
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


def cleanup_all_host_maestro_java(*, keep_pids: set[int] | None = None) -> list[int]:
    """Kill all Maestro CLI java processes on this host (legacy mode startup hygiene)."""
    if os.name != "nt":
        return []
    keep = keep_pids or set()
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='java.exe'\" | "
        "Where-Object { $_.CommandLine -and ($_.CommandLine -match 'maestro\\.cli\\.AppKt') } | "
        "ForEach-Object { [int]$_.ProcessId }"
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
            if pid in keep:
                continue
            terminate_process_tree(pid)
            unregister_owned_child_pid(pid)
            killed.append(pid)
            print(f"[ATP] host_maestro_java_killed pid={pid}", flush=True)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if killed:
        time.sleep(2.0)
    return killed


def wait_for_adb_forwards_stable(device_id: str, *, timeout_sec: float | None = None) -> bool:
    """Wait until device forward list is unchanged across consecutive samples."""
    timeout = timeout_sec if timeout_sec is not None else float(
        os.environ.get("ATP_ADB_FORWARD_STABLE_SEC", "20")
    )
    deadline = time.monotonic() + timeout
    prev: str | None = None
    stable = 0
    while time.monotonic() < deadline:
        cur = list_adb_forwards(device_id=device_id)
        if cur == prev:
            stable += 1
            if stable >= 2:
                print(
                    f"[ATP] adb_forward_stable device={_dev_log(device_id)} ok=True",
                    flush=True,
                )
                return True
        else:
            stable = 0
        prev = cur
        time.sleep(1.0)
    print(f"[ATP] adb_forward_stable device={_dev_log(device_id)} ok=False", flush=True)
    return False


def cleanup_orphan_maestro_java(
    device_id: str,
    *,
    keep_pids: set[int] | None = None,
) -> list[int]:
    """Kill Maestro java.exe for this device serial only; never touches unrelated java/adb."""
    keep = keep_pids or set()
    killed: list[int] = []
    for pid in _find_maestro_java_pids_for_device(device_id):
        if pid in keep:
            continue
        terminate_process_tree(pid)
        unregister_owned_child_pid(pid)
        killed.append(pid)
        print(f"[ATP] orphan_java_killed device={_dev_log(device_id)} pid={pid}", flush=True)
    return killed


def validate_device_health(device_id: str, *, suite_id: str, repo: Path) -> bool:
    """adb responsive + boot completed before Maestro startup."""
    if os.environ.get("ATP_DEVICE_HEALTH_CHECK", "1").strip().lower() in ("0", "false", "no", "off"):
        return True
    exe = _adb_exe()
    if not exe:
        print(f"[ATP] device_health_skip device={_dev_log(device_id)} reason=adb_not_found", flush=True)
        return True
    t0 = time.time()
    try:
        w = subprocess.run(
            [exe, "-s", device_id, "wait-for-device"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if w.returncode != 0:
            print(
                f"[ATP] device_health_fail device={_dev_log(device_id)} step=wait-for-device rc={w.returncode}",
                flush=True,
            )
            return False
        for _ in range(15):
            proc = subprocess.run(
                [exe, "-s", device_id, "shell", "getprop", "sys.boot_completed"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            val = (proc.stdout or "").strip()
            if val == "1":
                print(
                    f"[ATP] device_health_ok device={_dev_log(device_id)} boot_completed=1 "
                    f"elapsed_sec={time.time() - t0:.1f}",
                    flush=True,
                )
                return True
            time.sleep(1.0)
        print(f"[ATP] device_health_fail device={_dev_log(device_id)} step=boot_completed", flush=True)
        return False
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[ATP] device_health_fail device={_dev_log(device_id)} error={e}", flush=True)
        return False


def _log_byte_offset(log_path: Path) -> int:
    try:
        return log_path.stat().st_size if log_path.is_file() else 0
    except OSError:
        return 0


def _read_log_since(log_path: Path, start_offset: int, max_bytes: int = 65536) -> str:
    if not log_path.is_file():
        return ""
    try:
        size = log_path.stat().st_size
        if size <= start_offset:
            return ""
        with log_path.open("rb") as f:
            f.seek(start_offset)
            chunk = f.read(max_bytes)
        return chunk.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _startup_failed_in_log(text: str) -> str | None:
    if not text:
        return None
    if "TcpForwarder.waitFor" in text or "allocateForwarder" in text:
        return "tcp_forwarder"
    if "TimeoutException" in text and "tcpForward" in text:
        return "tcp_forward_timeout"
    if "7001" in text and "Connection refused" in text:
        return "localhost_7001_collision"
    if "Unknown options:" in text and ("driver-host-port" in text or "driver-port" in text):
        return "unsupported_driver_port_flag"
    if "SHGetKnownFolderPath" in text or "AppDirsException" in text:
        return "app_dirs"
    return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _probe_adb_shell_ok(device_id: str) -> bool:
    exe = _adb_exe()
    if not exe:
        return False
    try:
        proc = subprocess.run(
            [exe, "-s", device_id, "shell", "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        return proc.returncode == 0 and "ok" in (proc.stdout or "").lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe_host_port_listening(port: int) -> bool:
    if port <= 0:
        return False
    token = f":{port}"
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                if token in line and "LISTENING" in line.upper():
                    return True
            return False
        proc = subprocess.run(
            ["ss", "-ltn"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return token in (proc.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe_child_java_maestro(device_id: str, child_pid: int) -> bool:
    if os.name != "nt" or child_pid <= 0:
        return False
    dev = device_id.replace("'", "''")
    ps = (
        f"$d='{dev}'; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'java.exe' -and $_.CommandLine -and "
        "($_.CommandLine -match 'maestro\\.cli\\.AppKt') -and "
        "($_.CommandLine -match [regex]::Escape($d)) } | "
        "Select-Object -First 1 | ForEach-Object { $_.ProcessId }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return bool((proc.stdout or "").strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _match_ready_in_log(chunk: str, device_id: str) -> str | None:
    if not chunk or not chunk.strip():
        return None
    device_re = re.compile(rf"Running on\s+{re.escape(device_id)}\b", re.I)
    if device_re.search(chunk):
        return "running_on"
    patterns = [
        (r">\s*Flow\s+", "flow_marker"),
        (r"Launching\s+", "launching"),
        (r"Executing\s+", "executing"),
        (r"Android\s+Driver", "android_driver"),
        (r"Maestro\s+Android\s+driver", "maestro_android_driver"),
        (r"device\s+connected", "device_connected"),
        (r"COMPLETED\b", "completed"),
        (r"assertVisible", "yaml_step"),
        (r"tap\s+on", "yaml_tap"),
        (r"Starting\s+Maestro\s+test", "starting_maestro_test"),
    ]
    for pat, name in patterns:
        if re.search(pat, chunk, re.I):
            return name
    return None


def wait_for_maestro_session_ready(
    *,
    log_path: Path,
    device_id: str,
    log_start_offset: int = 0,
    timeout_sec: float | None = None,
    driver_port: int | None = None,
    child_pid: int | None = None,
    diagnostics: Any | None = None,
) -> tuple[bool, str]:
    """
    Poll per-flow Maestro log until session ready, with fallback health probes.

    Maestro output is redirected inside run_one_flow_on_device.bat; on Windows it may
    buffer. Fallbacks: log growth, adb echo, localhost driver port, java process probe.
    """
    timeout = timeout_sec if timeout_sec is not None else startup_ready_timeout_sec()
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    last_size = log_start_offset
    poll = 0
    fallback_after = min(25.0, timeout * 0.15)
    probe_port = driver_port if driver_port else 7001

    while time.monotonic() < deadline:
        poll += 1
        elapsed = time.monotonic() - started
        if child_pid and poll % 3 == 0 and not _pid_alive(child_pid):
            chunk = _read_log_since(log_path, log_start_offset)
            fail = _startup_failed_in_log(chunk) or "child_exited_early"
            return False, fail if isinstance(fail, str) else "child_exited_early"

        if diagnostics is not None:
            last_size = diagnostics.snapshot_flow_log(log_path, start_offset=last_size, label=f"poll_{poll}")

        chunk = _read_log_since(log_path, log_start_offset)
        fail = _startup_failed_in_log(chunk)
        if fail:
            if diagnostics is not None:
                diagnostics.trace("ready_fail_log", reason=fail)
            return False, fail

        marker = _match_ready_in_log(chunk, device_id)
        if marker:
            if diagnostics is not None:
                diagnostics.trace("ready_ok_log_marker", marker=marker, elapsed_sec=round(elapsed, 1))
            return True, marker

        try:
            cur_size = log_path.stat().st_size if log_path.is_file() else log_start_offset
        except OSError:
            cur_size = log_start_offset

        if elapsed >= fallback_after:
            if cur_size > log_start_offset + 400 and chunk.strip():
                if diagnostics is not None:
                    diagnostics.trace(
                        "ready_ok_log_growth",
                        bytes=cur_size - log_start_offset,
                        elapsed_sec=round(elapsed, 1),
                    )
                return True, "log_growth"
            if poll % 5 == 0 and _probe_adb_shell_ok(device_id):
                if diagnostics is not None:
                    diagnostics.trace("ready_ok_adb_echo", elapsed_sec=round(elapsed, 1))
                return True, "adb_echo_ok"
            if poll % 7 == 0 and _probe_host_port_listening(probe_port):
                if diagnostics is not None:
                    diagnostics.trace("ready_ok_host_port", port=probe_port, elapsed_sec=round(elapsed, 1))
                return True, "host_port_listen"
            if child_pid and poll % 9 == 0 and _probe_child_java_maestro(device_id, child_pid):
                if diagnostics is not None:
                    diagnostics.trace("ready_ok_java_maestro", child_pid=child_pid, elapsed_sec=round(elapsed, 1))
                return True, "java_maestro_process"

        if poll % 30 == 0:
            print(
                f"[ATP] startup_ready_poll device={_dev_log(device_id)} "
                f"elapsed_sec={elapsed:.1f} log_bytes={max(0, cur_size - log_start_offset)} "
                f"child_pid={child_pid or 0} driver_port={driver_port or probe_port}",
                flush=True,
            )
        time.sleep(1.0)

    if diagnostics is not None:
        diagnostics.trace("ready_timeout", wait_sec=round(timeout, 1), log_path=str(log_path))
    return False, "ready_timeout"


def terminate_process_tree(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        else:
            os.kill(pid, 15)
    except (OSError, subprocess.TimeoutExpired):
        pass


def prepare_device_for_maestro_startup(
    device_id: str,
    *,
    driver_port: int | None,
    suite_id: str,
    repo: Path,
    legacy_mode: bool = False,
) -> None:
    """ADB + port hygiene while holding startup lock (before Maestro subprocess)."""
    log_adb_forwards(device_id, "pre_startup")
    keep = get_owned_child_pids()
    if _kill_all_host_java_enabled():
        cleanup_all_host_maestro_java(keep_pids=keep)
    ok, detail = clear_device_adb_forwards(device_id)
    print(
        f"[ATP] adb_forward_cleanup device={_dev_log(device_id)} ok={ok} detail={detail!r}",
        flush=True,
    )
    if driver_port:
        port_free = wait_for_host_port_free(driver_port)
        print(
            f"[ATP] host_port_check device={_dev_log(device_id)} port={driver_port} free={port_free}",
            flush=True,
        )
    elif legacy_mode:
        wait_for_host_port_free(7001, timeout_sec=20.0)
    cleanup_orphan_maestro_java(device_id, keep_pids=keep)
    if legacy_mode:
        wait_for_adb_forwards_stable(device_id)
    log_adb_forwards(device_id, "post_cleanup")


def cleanup_after_startup_failure(
    device_id: str,
    *,
    repo: Path,
    suite_id: str,
    child_pid: int | None = None,
    driver_port: int | None = None,
) -> None:
    """Best-effort cleanup after failed Maestro session startup (forwards + owned child tree)."""
    if child_pid and is_owned_child_pid(child_pid):
        terminate_process_tree(child_pid)
        unregister_owned_child_pid(child_pid)
    elif child_pid:
        print(
            f"[ATP] startup_cleanup_skip_pid device={_dev_log(device_id)} pid={child_pid} reason=not_owned",
            flush=True,
        )
    log_adb_forwards(device_id, "startup_failure")
    ok, detail = clear_device_adb_forwards(device_id)
    print(
        f"[ATP] adb_forward_cleanup device={_dev_log(device_id)} phase=startup_failure ok={ok} detail={detail!r}",
        flush=True,
    )
    if driver_port:
        wait_for_host_port_free(driver_port, timeout_sec=15.0)
    cleanup_orphan_maestro_java(device_id, keep_pids={child_pid} if child_pid else set())
    print(f"[ATP] startup_cleanup_done device={_dev_log(device_id)} child_pid={child_pid or 0}", flush=True)


class MaestroStartupGate:
    """Context manager: acquire global startup lock until Maestro session is ready."""

    def __init__(
        self,
        *,
        device_id: str,
        flow_name: str,
        suite_id: str,
        repo: Path,
        launch_index: int,
        driver_port: int | None,
        device_count: int = 1,
    ) -> None:
        self.device_id = device_id
        self.flow_name = flow_name
        self.suite_id = suite_id
        self.repo = repo
        self.launch_index = launch_index
        self.driver_port = driver_port
        self.device_count = device_count
        self._enabled = startup_gate_enabled(device_count)
        self._legacy_mode = False
        self._acquired = False
        self._t_acquire: float | None = None

    def __enter__(self) -> MaestroStartupGate:
        if not self._enabled:
            return self
        self._t_acquire = time.time()
        print(
            f"[ATP] startup_lock_acquire device={_dev_log(self.device_id)} flow={self.flow_name} "
            f"driver_port_plan={self.driver_port} thread={threading.current_thread().name}",
            flush=True,
        )
        _startup_lock.acquire()
        self._acquired = True
        prepare_device_for_maestro_startup(
            self.device_id,
            driver_port=self.driver_port,
            suite_id=self.suite_id,
            repo=self.repo,
            legacy_mode=self._legacy_mode,
        )
        return self

    def set_legacy_mode(self, enabled: bool) -> None:
        self._legacy_mode = enabled

    def release_after_session_ready(
        self,
        *,
        log_path: Path,
        child_pid: int,
        log_start_offset: int = 0,
        diagnostics: Any | None = None,
    ) -> tuple[bool, str]:
        """
        Wait for log-ready while holding lock, apply stabilization delay, then release lock.
        Child process continues running (parallel YAML execution).
        """
        if not self._enabled:
            return True, "gate_disabled"
        try:
            t0 = time.time()
            ready, reason = wait_for_maestro_session_ready(
                log_path=log_path,
                device_id=self.device_id,
                log_start_offset=log_start_offset,
                driver_port=self.driver_port,
                child_pid=child_pid,
                diagnostics=diagnostics,
            )
            wait_sec = time.time() - t0
            if not ready:
                print(
                    f"[ATP] startup_ready_fail device={_dev_log(self.device_id)} flow={self.flow_name} "
                    f"reason={reason} wait_sec={wait_sec:.1f} child_pid={child_pid} "
                    f"log_offset={log_start_offset}",
                    flush=True,
                )
                if reason == "unsupported_driver_port_flag":
                    from .maestro_capabilities import (
                        invalidate_driver_port_support,
                        invalidate_isolated_runtime_support,
                    )

                    invalidate_driver_port_support(reason="unsupported_driver_port_flag")
                    invalidate_isolated_runtime_support(reason="unsupported_driver_port_flag")
                if reason in ("tcp_forwarder", "localhost_7001_collision"):
                    from .maestro_capabilities import invalidate_isolated_runtime_support

                    invalidate_isolated_runtime_support(reason=reason)
                return False, reason
            log_adb_forwards(self.device_id, "startup_ready")
            print(
                f"[ATP] startup_ready_ok device={_dev_log(self.device_id)} flow={self.flow_name} "
                f"reason={reason} wait_sec={wait_sec:.1f} child_pid={child_pid} "
                f"driver_port={self.driver_port}",
                flush=True,
            )
            delay = parallel_startup_delay_sec(
                legacy_mode=self._legacy_mode,
                device_count=self.device_count,
            )
            if delay > 0:
                print(
                    f"[ATP] startup_stabilization_delay device={_dev_log(self.device_id)} "
                    f"sleep_sec={delay:.1f}",
                    flush=True,
                )
                time.sleep(delay)
            held = time.time() - (self._t_acquire or time.time())
            print(
                f"[ATP] startup_lock_release device={_dev_log(self.device_id)} flow={self.flow_name} "
                f"held_sec={held:.1f}",
                flush=True,
            )
            return True, reason
        finally:
            if self._acquired:
                _startup_lock.release()
                self._acquired = False

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._acquired:
            print(
                f"[ATP] startup_lock_release_abort device={_dev_log(self.device_id)} flow={self.flow_name}",
                flush=True,
            )
            _startup_lock.release()
            self._acquired = False
