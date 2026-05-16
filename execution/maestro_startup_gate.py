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
import threading
import time
from pathlib import Path
from typing import Any

_startup_lock = threading.Lock()
_owned_child_pids: set[int] = set()
_owned_pids_lock = threading.Lock()


def startup_gate_enabled() -> bool:
    return os.environ.get("ATP_MAESTRO_STARTUP_GATE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def parallel_startup_delay_sec(*, legacy_mode: bool = False) -> float:
    if legacy_mode:
        raw = (os.environ.get("MAESTRO_PARALLEL_STARTUP_DELAY_SEC") or "8").strip()
    else:
        raw = (os.environ.get("MAESTRO_PARALLEL_STARTUP_DELAY_SEC") or "5").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 8.0 if legacy_mode else 5.0


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
        f"[ATP] adb_forward_list phase={phase} device={device_id}\n"
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
                    f"[ATP] adb_forward_stable device={device_id} ok=True",
                    flush=True,
                )
                return True
        else:
            stable = 0
        prev = cur
        time.sleep(1.0)
    print(f"[ATP] adb_forward_stable device={device_id} ok=False", flush=True)
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
        print(f"[ATP] orphan_java_killed device={device_id} pid={pid}", flush=True)
    return killed


def validate_device_health(device_id: str, *, suite_id: str, repo: Path) -> bool:
    """adb responsive + boot completed before Maestro startup."""
    if os.environ.get("ATP_DEVICE_HEALTH_CHECK", "1").strip().lower() in ("0", "false", "no", "off"):
        return True
    exe = _adb_exe()
    if not exe:
        print(f"[ATP] device_health_skip device={device_id} reason=adb_not_found", flush=True)
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
                f"[ATP] device_health_fail device={device_id} step=wait-for-device rc={w.returncode}",
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
                    f"[ATP] device_health_ok device={device_id} boot_completed=1 "
                    f"elapsed_sec={time.time() - t0:.1f}",
                    flush=True,
                )
                return True
            time.sleep(1.0)
        print(f"[ATP] device_health_fail device={device_id} step=boot_completed", flush=True)
        return False
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[ATP] device_health_fail device={device_id} error={e}", flush=True)
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
    if "Unknown options:" in text and ("driver-host-port" in text or "driver-port" in text):
        return "unsupported_driver_port_flag"
    if "SHGetKnownFolderPath" in text or "AppDirsException" in text:
        return "app_dirs"
    return None


def wait_for_maestro_session_ready(
    *,
    log_path: Path,
    device_id: str,
    log_start_offset: int = 0,
    timeout_sec: float | None = None,
    driver_port: int | None = None,
) -> tuple[bool, str]:
    """
    Poll per-flow Maestro log (only bytes written after log_start_offset) until session ready.
    Prefers '> Flow' over 'Running on' to ensure driver IPC is established.
    """
    timeout = timeout_sec if timeout_sec is not None else startup_ready_timeout_sec()
    deadline = time.monotonic() + timeout
    device_re = re.compile(rf"Running on\s+{re.escape(device_id)}\b", re.I)
    flow_re = re.compile(r">\s*Flow\s+", re.I)
    while time.monotonic() < deadline:
        chunk = _read_log_since(log_path, log_start_offset)
        fail = _startup_failed_in_log(chunk)
        if fail:
            return False, fail
        if flow_re.search(chunk):
            return True, "flow_marker"
        if device_re.search(chunk):
            # Accept Running on only after half timeout if > Flow never appears (slow devices)
            if time.monotonic() > deadline - (timeout * 0.5):
                return True, "running_on"
        time.sleep(1.0)
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
    if legacy_mode:
        cleanup_all_host_maestro_java(keep_pids=set())
    ok, detail = clear_device_adb_forwards(device_id)
    print(
        f"[ATP] adb_forward_cleanup device={device_id} ok={ok} detail={detail!r}",
        flush=True,
    )
    if driver_port:
        port_free = wait_for_host_port_free(driver_port)
        print(
            f"[ATP] host_port_check device={device_id} port={driver_port} free={port_free}",
            flush=True,
        )
    elif legacy_mode:
        wait_for_host_port_free(7001, timeout_sec=20.0)
    cleanup_orphan_maestro_java(device_id, keep_pids=set())
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
            f"[ATP] startup_cleanup_skip_pid device={device_id} pid={child_pid} reason=not_owned",
            flush=True,
        )
    log_adb_forwards(device_id, "startup_failure")
    ok, detail = clear_device_adb_forwards(device_id)
    print(
        f"[ATP] adb_forward_cleanup device={device_id} phase=startup_failure ok={ok} detail={detail!r}",
        flush=True,
    )
    if driver_port:
        wait_for_host_port_free(driver_port, timeout_sec=15.0)
    cleanup_orphan_maestro_java(device_id, keep_pids={child_pid} if child_pid else set())
    print(f"[ATP] startup_cleanup_done device={device_id} child_pid={child_pid or 0}", flush=True)


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
    ) -> None:
        self.device_id = device_id
        self.flow_name = flow_name
        self.suite_id = suite_id
        self.repo = repo
        self.launch_index = launch_index
        self.driver_port = driver_port
        self._enabled = startup_gate_enabled()
        self._legacy_mode = False
        self._acquired = False
        self._t_acquire: float | None = None

    def __enter__(self) -> MaestroStartupGate:
        if not self._enabled:
            return self
        self._t_acquire = time.time()
        print(
            f"[ATP] startup_lock_acquire device={self.device_id} flow={self.flow_name} "
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
            )
            wait_sec = time.time() - t0
            if not ready:
                print(
                    f"[ATP] startup_ready_fail device={self.device_id} flow={self.flow_name} "
                    f"reason={reason} wait_sec={wait_sec:.1f} child_pid={child_pid} "
                    f"log_offset={log_start_offset}",
                    flush=True,
                )
                if reason == "unsupported_driver_port_flag":
                    from .maestro_capabilities import invalidate_driver_port_support

                    invalidate_driver_port_support(reason="unsupported_driver_port_flag")
                return False, reason
            log_adb_forwards(self.device_id, "startup_ready")
            print(
                f"[ATP] startup_ready_ok device={self.device_id} flow={self.flow_name} "
                f"reason={reason} wait_sec={wait_sec:.1f} child_pid={child_pid} "
                f"driver_port={self.driver_port}",
                flush=True,
            )
            delay = parallel_startup_delay_sec(legacy_mode=self._legacy_mode)
            if delay > 0:
                print(
                    f"[ATP] startup_stabilization_delay device={self.device_id} "
                    f"sleep_sec={delay:.1f}",
                    flush=True,
                )
                time.sleep(delay)
            held = time.time() - (self._t_acquire or time.time())
            print(
                f"[ATP] startup_lock_release device={self.device_id} flow={self.flow_name} "
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
                f"[ATP] startup_lock_release_abort device={self.device_id} flow={self.flow_name}",
                flush=True,
            )
            _startup_lock.release()
            self._acquired = False
