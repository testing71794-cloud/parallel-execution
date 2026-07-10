#!/usr/bin/env python3
"""
Blocking ATP orchestration for Jenkins (Stack A entry for Maestro lifecycle).

Replaces the detached PowerShell Start-Process chain for ATP runs while
preserving scripts/run_one_flow_on_device.bat outputs (reports/, status/, CSV).

Does not modify Maestro YAML, Excel schema, AI logic, or report layouts.

Execution models (ATP_SCHEDULER + ATP_DEVICE_EXECUTION):
  dynamic (default): per-device worker pool with rotated (flow x device) queue — max utilization.
  wave (legacy):     flow-level barrier — all devices finish flow N before flow N+1.
  sequential:        one device at a time per flow (legacy).
  Per-device isolated subprocess, logs, status, maestro-debug (maestro_runner.py).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .atp_dynamic_scheduler import (
    DynamicDeviceScheduler,
    FlowDeviceTask,
    TaskOutcome,
    build_rotated_device_queues,
)
from .device_lease import DeviceLease, cleanup_stale_device_leases, release_device_lease
from .maestro_capabilities import (
    apply_native_parallel_env_defaults,
    assert_native_parallel_ready,
    detect_maestro_capabilities,
    driver_host_port_supported,
    native_parallel_active,
)
from .maestro_runner import (
    WorkerState,
    _status_file_path,
    log_lifecycle,
    post_run_validate,
    pre_maestro_cleanup,
    resolve_maestro_launcher,
    run_run_one_flow_device_bat,
)
from .atp_folder_paths import discover_atp_yaml_files, resolve_atp_subfolder
from .flow_timing import read_status_fields

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils.device_utils import get_device_display_name  # noqa: E402
from utils.git_branch import detect_git_branch, write_git_branch_file  # noqa: E402

_GIT_BRANCH: str | None = None


def _atp_git_branch(repo: Path) -> str:
    global _GIT_BRANCH
    if _GIT_BRANCH is None:
        _GIT_BRANCH = detect_git_branch(repo)
        os.environ["ATP_GIT_BRANCH"] = _GIT_BRANCH
        write_git_branch_file(repo, _GIT_BRANCH)
    return _GIT_BRANCH


def _dev_log(device_id: str) -> str:
    return get_device_display_name(device_id)


# Bump when orchestration semantics change (visible in Jenkins console).
def _read_orchestrator_rev() -> str:
    rev_file = Path(__file__).resolve().parent / "ORCHESTRATOR_REV.txt"
    if rev_file.is_file():
        line = rev_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if line and line[0].strip():
            return line[0].strip()
    return "unknown"


ORCHESTRATOR_REV = _read_orchestrator_rev()


def configure_stdout_stderr_utf8() -> None:
    """Best-effort UTF-8 stdout/stderr on Windows Jenkins agents (avoids cp1252 encode crashes)."""
    if os.name != "nt":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # PYTHONIOENCODING=utf-8 is set in some Jenkins stages; honor when streams lack reconfigure.
    if os.environ.get("PYTHONIOENCODING", "").strip().lower().replace("-", "") != "utf8":
        try:
            import io

            for name in ("stdout", "stderr"):
                stream = getattr(sys, name, None)
                if stream is None or not hasattr(stream, "buffer"):
                    continue
                enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
                if enc == "utf8":
                    continue
                wrapped = io.TextIOWrapper(
                    stream.buffer,
                    encoding="utf-8",
                    errors="replace",
                    line_buffering=True,
                )
                setattr(sys, name, wrapped)
        except Exception:
            pass


def _sanitize_console_text(text: str) -> str:
    """Replace characters the active console encoding cannot represent."""
    payload = "" if text is None else str(text)
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        sanitized = payload.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        sanitized = payload.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    return sanitized.replace("\ufffd", "?")


def safe_print(text: str, *, file=None, flush: bool = True) -> None:
    """Print without raising when Jenkins/console encoding rejects log content."""
    target = file if file is not None else sys.stdout
    payload = "" if text is None else str(text)
    try:
        print(payload, file=target, flush=flush)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return
    try:
        print(_sanitize_console_text(payload), file=target, flush=flush)
    except Exception:
        try:
            ascii_payload = payload.encode("ascii", errors="replace").decode("ascii")
            print(ascii_payload, file=target, flush=flush)
        except Exception:
            return


def _validate_execution_modules() -> bool:
    """Fail fast when execution stack modules are missing from the Jenkins workspace checkout."""
    execution_dir = Path(__file__).resolve().parent
    print(f"[ATP] execution_package_dir={execution_dir}", flush=True)
    try:
        import execution
        import execution.maestro_stabilization as ms
    except ModuleNotFoundError as exc:
        print(f"[ATP] ERROR: execution stack import failed: {exc}", flush=True)
        stabilization_py = execution_dir / "maestro_stabilization.py"
        print(
            f"[ATP] maestro_stabilization_expected={stabilization_py} "
            f"exists={stabilization_py.is_file()}",
            flush=True,
        )
        return False
    print(f"[ATP] execution_package={Path(execution.__file__).resolve().parent}", flush=True)
    print(f"[ATP] maestro_stabilization={Path(ms.__file__).resolve()}", flush=True)
    return True


def add_adb_from_env_to_path() -> None:
    d = os.environ.get("ADB_HOME", "").strip().strip('"')
    if not d:
        return
    adb = Path(d) / ("adb.exe" if os.name == "nt" else "adb")
    if not adb.is_file():
        return
    sep = os.pathsep
    cur = os.environ.get("PATH", "")
    parts = cur.split(sep) if cur else []
    if d in parts or d.rstrip("\\/") in parts:
        return
    os.environ["PATH"] = d + sep + cur


def get_authorized_serials_from_adb() -> list[str]:
    from .subprocess_launch import resolve_adb_executable

    adb = resolve_adb_executable()
    if not adb:
        raise RuntimeError("adb not on PATH. Set ADB_HOME or ANDROID_HOME/platform-tools.")
    proc = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=60, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"adb devices failed (exit {proc.returncode})")
    text = proc.stdout or ""
    serials: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(\S+)\s+device\s*$", line)
        if m:
            serials.append(m.group(1).strip())
    return serials


def read_detected_file_serials(repo: Path) -> list[str]:
    detected = repo / "detected_devices.txt"
    if not detected.is_file():
        return []
    raw = detected.read_text(encoding="utf-8", errors="replace").splitlines()
    skip = re.compile(r"^(List of devices attached|Devices detected:|Device list saved to:)", re.I)
    serial_list: list[str] = []
    seen: set[str] = set()
    for line in raw:
        t = line.strip()
        if t and len(t) > 0 and ord(t[0]) == 0xFEFF:
            t = t[1:].strip()
        if not t or skip.search(t):
            continue
        if re.match(r"^\S+$", t) and t not in seen:
            seen.add(t)
            serial_list.append(t)
    return serial_list


def merge_and_pick_devices_with_app_preflight(repo: Path, app_id: str) -> list[str]:
    """``merge_and_pick_devices`` then drop devices missing ``app_id`` (non-fatal)."""
    devices = merge_and_pick_devices(repo)
    if not (app_id or "").strip():
        return devices
    if os.environ.get("ATP_DEVICE_APP_PREFLIGHT", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return devices
    from .device_app_preflight import filter_devices_with_app

    ready, missing = filter_devices_with_app(devices, app_id, repo=repo)
    if missing and ready:
        print(
            f"[ATP] device_app_preflight: continuing with {len(ready)} device(s); "
            f"skipped {len(missing)} without app",
            flush=True,
        )
    return ready


def merge_and_pick_devices(repo: Path) -> list[str]:
    """Live ``adb devices`` is authoritative; detected_devices.txt may filter but never shrink below adb."""
    authorized = get_authorized_serials_from_adb()
    if not authorized:
        raise RuntimeError("No Android devices in state 'device'.")
    file_serials = read_detected_file_serials(repo)
    print(
        f"[ATP] devices adb={len(authorized)} [{', '.join(_dev_log(s) for s in authorized)}] "
        f"detected_file={len(file_serials)} "
        f"[{', '.join(_dev_log(s) for s in file_serials) if file_serials else '-'}]",
        flush=True,
    )
    if not file_serials:
        return list(authorized)
    picked = [s for s in file_serials if s in authorized]
    if not picked:
        print(
            f"[ATP] WARN: detected_devices.txt serial(s) not in current adb devices: "
            f"{', '.join(_dev_log(s) for s in file_serials)}",
            flush=True,
        )
        print(
            f"[ATP] WARN: falling back to all authorized device(s): "
            f"{', '.join(_dev_log(s) for s in authorized)}",
            flush=True,
        )
        return list(authorized)
    if len(picked) < len(file_serials):
        missing = [s for s in file_serials if s not in picked]
        print(
            f"[ATP] WARN: dropping stale serial(s) from detected_devices.txt: "
            f"{', '.join(_dev_log(s) for s in missing)}",
            flush=True,
        )
    # Hybrid: Detect stage may have run on another agent with a stale one-device file while this agent has N USB devices.
    if len(authorized) > len(picked):
        print(
            f"[ATP] WARN: live adb has {len(authorized)} device(s) but detected_devices.txt matched "
            f"{len(picked)}; using all authorized adb devices for this run",
            flush=True,
        )
        return list(authorized)
    return picked


def get_atp_folder_name(atp_root: Path, file_path: Path) -> str:
    root_full = atp_root.resolve()
    file_full = file_path.resolve()
    try:
        rest = str(file_full.relative_to(root_full))
    except ValueError:
        return "_Invalid"
    rest = rest.lstrip("/\\")
    if not rest:
        return "_Root"
    first = re.split(r"[\\/]", rest, maxsplit=1)[0]
    if re.match(r".*\.(yaml|yml)$", first, re.I):
        return "_Root"
    return first


def get_atp_suite_id(folder_name: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "_", folder_name.strip()).strip("_").lower() or "unknown"
    return f"atp_{t}"


def merge_atp_suite_labels_json(labels_path: Path, new_labels: dict[str, str], merge_existing: bool) -> None:
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    h: dict[str, str] = {}
    if merge_existing and labels_path.is_file():
        try:
            raw = labels_path.read_text(encoding="utf-8", errors="replace")
            o = json.loads(raw) if raw.strip() else {}
            if isinstance(o, dict):
                for k, v in o.items():
                    h[str(k)] = str(v)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[ATP] WARN: could not read existing labels JSON, rewriting: {e}", flush=True)
    h.update(new_labels)
    labels_path.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")


def discover_flows(repo: Path, atp_subfolder: str) -> list[Path]:
    atp_root = repo / "ATP TestCase Flows"
    folder_arg = (atp_subfolder or "").strip()
    resolved = resolve_atp_subfolder(repo, folder_arg) if folder_arg else ""
    print(f"[ATP] workspace={repo.resolve()}", flush=True)
    print(f"[ATP] atp_root={atp_root.resolve()}", flush=True)
    if folder_arg:
        print(f"[ATP] folder_arg={folder_arg!r} resolved_folder={resolved!r}", flush=True)
    if not atp_root.is_dir():
        print("[ATP] ERROR: folder not found - ATP TestCase Flows", flush=True)
        return []
    if folder_arg:
        folder_root = atp_root / resolved
        if not folder_root.is_dir():
            print(
                f"[ATP] ERROR: subfolder not found on disk: {resolved!r} "
                f"(from stage arg {folder_arg!r})",
                flush=True,
            )
            available = [c.name for c in sorted(atp_root.iterdir()) if c.is_dir()]
            print(f"[ATP] available ATP folders: {available}", flush=True)
            return []
    flows = discover_atp_yaml_files(repo, folder_arg, exclude_subflows=True)
    include = (os.environ.get("ATP_FLOW_INCLUDE") or "").strip()
    exclude = (os.environ.get("ATP_FLOW_EXCLUDE") or "").strip()
    if include:
        print(f"[ATP] ATP_FLOW_INCLUDE filter={include!r} -> {len(flows)} flow(s)", flush=True)
    if exclude:
        print(f"[ATP] ATP_FLOW_EXCLUDE filter={exclude!r} -> {len(flows)} flow(s)", flush=True)
    if flows:
        print(f"[ATP] discovered {len(flows)} yaml test file(s):", flush=True)
        for p in flows:
            try:
                rel = p.resolve().relative_to(repo.resolve())
            except ValueError:
                rel = p
            print(f"[ATP]   - {rel}", flush=True)
    else:
        print("[ATP] discovered 0 yaml test files (subflows/ excluded)", flush=True)
    return flows


def write_section(title: str) -> None:
    print("", flush=True)
    print("=====================================", flush=True)
    print(title, flush=True)
    print("=====================================", flush=True)


def _safe_flow_stem(flow: Path) -> str:
    from execution.atp_folder_paths import safe_flow_stem

    return safe_flow_stem(flow.stem)


def _log_path(repo: Path, suite_id: str, flow: Path, device_id: str) -> Path:
    safe_dev = re.sub(r"\s+", "_", device_id)
    return repo / "reports" / suite_id / "logs" / f"{_safe_flow_stem(flow)}_{safe_dev}.log"


def _read_log_tail_text(repo: Path, suite_id: str, flow: Path, device_id: str, n: int) -> str:
    lp = _log_path(repo, suite_id, flow, device_id)
    if not lp.is_file():
        return ""
    try:
        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


@dataclass(frozen=True)
class _DeviceFlowOutcome:
    device_id: str
    exit_code: int


def _default_parallel_stagger_sec(device_count: int = 1) -> str:
    """Default startup stagger step (seconds per device index); execution stays parallel."""
    if device_count > 1:
        return "2"
    return "0"


def _parallel_launch_stagger_sec(launch_index: int) -> float:
    """Startup-only stagger between device workers (does not serialize flow execution)."""
    from .maestro_stabilization import parallel_device_stagger_sec

    return parallel_device_stagger_sec(launch_index)


def _handshake_gate_enabled(device_count: int, mode: str) -> bool:
    if mode != "parallel" or device_count <= 1:
        return False
    try:
        from .maestro_capabilities import is_native_parallel_env_active, native_parallel_active

        if is_native_parallel_env_active() or native_parallel_active(device_count):
            return False
    except ImportError:
        pass
    raw = (os.environ.get("ATP_MAESTRO_HANDSHAKE_GATE") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    # Legacy default: Windows serialized handshake only when not in native parallel mode.
    return os.name == "nt"


def _wait_for_prior_device_handshake(
    *,
    repo: Path,
    suite_id: str,
    flow: Path,
    devices: list[str],
    launch_index: int,
) -> None:
    """
    Device index > 0 waits until the prior device's Maestro log shows driver session started.
    Serializes only the risky handshake window; tests still run concurrently afterward.
    """
    if launch_index <= 0 or launch_index >= len(devices):
        return
    prior = devices[launch_index - 1]
    timeout = float(os.environ.get("ATP_MAESTRO_HANDSHAKE_GATE_SEC", "120"))
    deadline = time.monotonic() + timeout
    wait_t0 = time.monotonic()
    markers = ("Running on", "Launch app", "Flow ", "COMPLETED", "FAILED")
    print(
        f"[ATP] handshake_gate device={_dev_log(devices[launch_index])} "
        f"waits_for={_dev_log(prior)} flow={flow.stem}",
        flush=True,
    )
    while time.monotonic() < deadline:
        tail = _read_log_tail_text(repo, suite_id, flow, prior, 40)
        if tail and any(m in tail for m in markers):
            print(
                f"[ATP] handshake_gate open device={_dev_log(devices[launch_index])} "
                f"prior={_dev_log(prior)} waited_sec={time.monotonic() - wait_t0:.1f}",
                flush=True,
            )
            return
        time.sleep(1.5)
    print(
        f"[ATP] handshake_gate timeout device={_dev_log(devices[launch_index])} "
        f"prior={_dev_log(prior)} after_sec={timeout:.0f} — launching Maestro anyway",
        flush=True,
    )


def _scheduler_mode() -> str:
    """
    dynamic = per-device worker pool (default, max utilization).
    wave    = synchronized flow waves (rollback: ATP_SCHEDULER=wave).
    """
    raw = (os.environ.get("ATP_SCHEDULER") or "dynamic").strip().lower()
    if raw in ("wave", "flow_wave", "barrier", "legacy"):
        return "wave"
    return "dynamic"


def _device_execution_mode(device_count: int) -> str:
    """
    parallel = flow-level fan-out to all devices (default when device_count > 1).
    sequential = legacy one-device-at-a-time per flow (ATP_DEVICE_EXECUTION=sequential).
    """
    raw = (os.environ.get("ATP_DEVICE_EXECUTION") or "parallel").strip().lower()
    if raw in ("sequential", "seq", "0", "false", "no", "off"):
        return "sequential"
    if device_count <= 1:
        return "sequential"
    return "parallel"


def _execute_flow_on_device(
    *,
    repo: Path,
    suite_id: str,
    flow: Path,
    flow_base: str,
    devices: list[str],
    device_id: str,
    app_id: str,
    clear_state: str,
    maestro_launch: Path,
    allow_maestro_kill: bool,
    launch_index: int = 0,
    execution_mode: str = "parallel",
    worker_startup: bool = False,
) -> _DeviceFlowOutcome:
    """One (flow, device) run: lease, isolated subprocess, per-device reports (no shared state)."""
    from .maestro_stabilization import maybe_startup_stagger_once

    maybe_startup_stagger_once(device_id, launch_index)
    try:
        from utils.runflow_resolve import validate_runflow_paths

        validate_runflow_paths(flow, repo_root=repo)
    except (OSError, ImportError) as exc:
        print(f"[ATP] runflow_resolve_skip flow={flow_base} error={exc}", flush=True)
    if execution_mode != "dynamic" and _handshake_gate_enabled(len(devices), execution_mode):
        _wait_for_prior_device_handshake(
            repo=repo,
            suite_id=suite_id,
            flow=flow,
            devices=devices,
            launch_index=launch_index,
        )
    rd = repo / "reports" / suite_id
    (rd / "logs").mkdir(parents=True, exist_ok=True)
    (rd / "results").mkdir(parents=True, exist_ok=True)

    lease = DeviceLease.for_serial(repo, device_id)
    exit_code = 1
    t0 = time.time()
    try:
        log_lifecycle(
            repo, suite_id, WorkerState.ALLOCATED, "lease acquire", device=device_id, flow=flow_base
        )
        lease.acquire()
        print(
            f"[ATP] device_run_start device={_dev_log(device_id)} flow={flow_base} "
            f"thread={threading.current_thread().name} ts={t0:.3f}",
            flush=True,
        )
        log_lifecycle(repo, suite_id, WorkerState.PREPARING, "preparing", device=device_id, flow=flow_base)
        pre_maestro_cleanup(device_id, suite_id, repo, allow_maestro_kill=allow_maestro_kill)
        log_lifecycle(
            repo, suite_id, WorkerState.RUNNING, "invoke run_one_flow_on_device.bat", device=device_id
        )
        exit_code = run_run_one_flow_device_bat(
            repo=repo,
            suite_id=suite_id,
            flow_path=flow,
            device_id=device_id,
            app_id=app_id,
            clear_state=clear_state,
            maestro_launcher=maestro_launch,
            launch_index=launch_index,
            device_count=len(devices),
        )
    finally:
        release_device_lease(lease)
        log_lifecycle(repo, suite_id, WorkerState.IDLE, "lease released", device=device_id)
        print(
            f"[ATP] device_run_end device={_dev_log(device_id)} flow={flow_base} exit={exit_code} "
            f"elapsed_sec={time.time() - t0:.1f}",
            flush=True,
        )

    return _DeviceFlowOutcome(device_id=device_id, exit_code=exit_code)


def _run_flow_wave_on_devices(
    *,
    repo: Path,
    suite_id: str,
    flow: Path,
    flow_base: str,
    devices: list[str],
    app_id: str,
    clear_state: str,
    maestro_launch: Path,
) -> list[_DeviceFlowOutcome]:
    """Synchronized barrier: all devices finish this flow before the caller starts the next flow."""
    mode = _device_execution_mode(len(devices))
    allow_maestro_kill = len(devices) <= 1
    wave_t0 = time.time()
    print(
        f"[ATP] flow_wave_start flow={flow_base} mode={mode} device_count={len(devices)} ts={wave_t0:.3f}",
        flush=True,
    )
    if mode == "parallel":
        print(
            f"  [ATP] flow wave parallel: {flow_base} on {len(devices)} device(s): "
            f"{', '.join(_dev_log(d) for d in devices)}",
            flush=True,
        )
        outcomes: list[_DeviceFlowOutcome] = []
        with ThreadPoolExecutor(max_workers=len(devices), thread_name_prefix="atp-flow") as pool:
            for dev in devices:
                print(
                    f"  [ATP] threadpool_submit device={_dev_log(dev)} flow={flow_base} ts={time.time():.3f}",
                    flush=True,
                )
            futures = {
                pool.submit(
                    _execute_flow_on_device,
                    repo=repo,
                    suite_id=suite_id,
                    flow=flow,
                    flow_base=flow_base,
                    devices=devices,
                    device_id=dev,
                    app_id=app_id,
                    clear_state=clear_state,
                    maestro_launch=maestro_launch,
                    allow_maestro_kill=allow_maestro_kill,
                    launch_index=idx,
                    execution_mode=mode,
                ): dev
                for idx, dev in enumerate(devices)
            }
            for fut in as_completed(futures):
                try:
                    outcomes.append(fut.result())
                except Exception as exc:
                    dev = futures[fut]
                    print(
                        f"  [FAIL] device={_dev_log(dev)} flow={flow_base} orchestrator error: {exc}",
                        flush=True,
                    )
                    outcomes.append(_DeviceFlowOutcome(device_id=dev, exit_code=1))
        order = {d: i for i, d in enumerate(devices)}
        outcomes.sort(key=lambda o: order.get(o.device_id, 999))
        wave_elapsed = time.time() - wave_t0
        print(
            f"[ATP] flow_wave_barrier_done flow={flow_base} mode=parallel "
            f"elapsed_sec={wave_elapsed:.1f}",
            flush=True,
        )
        _print_wave_summary(
            flow_base,
            outcomes,
            wave_elapsed,
            repo=repo,
            suite_id=suite_id,
            flow=flow,
        )
        return outcomes

    print(f"  [ATP] flow wave sequential: {flow_base}", flush=True)
    seq_outcomes: list[_DeviceFlowOutcome] = []
    for dev in devices:
        print(f"  device {_dev_log(dev)}", flush=True)
        seq_outcomes.append(
            _execute_flow_on_device(
                repo=repo,
                suite_id=suite_id,
                flow=flow,
                flow_base=flow_base,
                devices=devices,
                device_id=dev,
                app_id=app_id,
                clear_state=clear_state,
                maestro_launch=maestro_launch,
                allow_maestro_kill=True,
                launch_index=0,
                execution_mode=mode,
            )
        )
    print(
        f"[ATP] flow_wave_barrier_done flow={flow_base} mode=sequential "
        f"elapsed_sec={time.time() - wave_t0:.1f}",
        flush=True,
    )
    return seq_outcomes


def _execute_task_for_scheduler(
    *,
    repo: Path,
    devices: list[str],
    app_id: str,
    clear_state: str,
    maestro_launch: Path,
    task: FlowDeviceTask,
    device_index: int,
    worker_startup: bool,
) -> TaskOutcome:
    outcome = _execute_flow_on_device(
        repo=repo,
        suite_id=task.suite_id,
        flow=task.flow,
        flow_base=task.flow_base,
        devices=devices,
        device_id=task.device_id,
        app_id=app_id,
        clear_state=clear_state,
        maestro_launch=maestro_launch,
        allow_maestro_kill=False,
        launch_index=device_index,
        execution_mode="dynamic",
        worker_startup=worker_startup,
    )
    return TaskOutcome(device_id=outcome.device_id, exit_code=outcome.exit_code)


def _run_dynamic_worker_pool(
    *,
    repo: Path,
    atp_root: Path,
    flows: list[Path],
    devices: list[str],
    app_id: str,
    clear_state: str,
    maestro_launch: Path,
    labels: dict[str, str],
) -> bool:
    """Returns True if any failure."""
    queues = build_rotated_device_queues(
        flows=flows,
        devices=devices,
        atp_root=atp_root,
        folder_name_fn=get_atp_folder_name,
        suite_id_fn=get_atp_suite_id,
    )
    for flow in flows:
        folder_name = get_atp_folder_name(atp_root, flow)
        labels[get_atp_suite_id(folder_name)] = folder_name

    def write_flow_section(task: FlowDeviceTask) -> None:
        write_section(f"ATP [{task.folder_name}] :: {task.flow_base} (suite={task.suite_id})")
        log_lifecycle(repo, task.suite_id, WorkerState.IDLE, "dynamic task", flow=task.flow_base)

    def report_task(task: FlowDeviceTask, outcome: TaskOutcome) -> bool:
        return _report_device_outcome(
            repo,
            task.suite_id,
            task.flow,
            task.flow_base,
            _DeviceFlowOutcome(device_id=outcome.device_id, exit_code=outcome.exit_code),
        )

    scheduler = DynamicDeviceScheduler(
        repo=repo,
        devices=devices,
        device_queues=queues,
        execute_task=lambda task, device_index, worker_startup: _execute_task_for_scheduler(
            repo=repo,
            devices=devices,
            app_id=app_id,
            clear_state=clear_state,
            maestro_launch=maestro_launch,
            task=task,
            device_index=device_index,
            worker_startup=worker_startup,
        ),
        report_outcome=report_task,
        write_flow_section=write_flow_section,
        worker_stagger_sec_fn=_parallel_launch_stagger_sec,
    )
    _sched_out, failed = scheduler.run()
    return failed


def _print_wave_summary(
    flow_base: str,
    outcomes: list[_DeviceFlowOutcome],
    elapsed_sec: float,
    *,
    repo: Path | None = None,
    suite_id: str = "",
    flow: Path | None = None,
) -> None:
    """Deterministic per-wave rollup (device order preserved)."""
    ok = sum(1 for o in outcomes if o.exit_code == 0)
    skip = 0
    if repo is not None and suite_id and flow is not None:
        skip = sum(
            1
            for o in outcomes
            if o.exit_code != 0 and _outcome_is_app_skip(o.exit_code, repo, suite_id, flow, o.device_id)
        )
    fail = len(outcomes) - ok - skip
    print(
        f"[ATP] wave_summary flow={flow_base} devices={len(outcomes)} ok={ok} skip={skip} fail={fail} "
        f"wall_sec={elapsed_sec:.1f}",
        flush=True,
    )
    for o in outcomes:
        if o.exit_code == 0:
            mark = "OK"
        elif (
            repo is not None
            and suite_id
            and flow is not None
            and _outcome_is_app_skip(o.exit_code, repo, suite_id, flow, o.device_id)
        ):
            mark = "SKIP"
        else:
            mark = "FAIL"
        print(
            f"[ATP] wave_device_result device={_dev_log(o.device_id)} exit={o.exit_code} {mark}",
            flush=True,
        )


def _outcome_is_app_skip(exit_code: int, repo: Path, suite_id: str, flow: Path, device_id: str) -> bool:
    from .device_app_preflight import EXIT_APP_NOT_INSTALLED

    if exit_code == EXIT_APP_NOT_INSTALLED:
        return True
    try:
        reason = read_status_fields(_status_file_path(repo, suite_id, flow, device_id)).get(
            "reason", ""
        )
        return reason.strip().upper() == "APP_NOT_INSTALLED"
    except Exception:
        return False


def _report_device_outcome(
    repo: Path,
    suite_id: str,
    flow: Path,
    flow_base: str,
    outcome: _DeviceFlowOutcome,
) -> bool:
    """Print console result for one device; return True if failed (not skipped)."""
    dev = outcome.device_id
    ex = outcome.exit_code
    dur_hint = ""
    try:
        st = _status_file_path(repo, suite_id, flow, dev)
        dm = read_status_fields(st).get("duration_ms", "")
        if dm:
            dur_hint = f" duration_ms={dm}"
    except Exception:
        pass
    if ex != 0 and _outcome_is_app_skip(ex, repo, suite_id, flow, dev):
        print(
            f"  [SKIP] exit={ex} device={_dev_log(dev)} flow={flow_base} "
            f"reason=APP_NOT_INSTALLED{dur_hint}",
            flush=True,
        )
        return False
    if ex != 0:
        safe_print(f"  [FAIL] exit={ex} device={_dev_log(dev)} flow={flow_base}{dur_hint}")
        try:
            _print_log_tail(repo, suite_id, flow, dev)
        except Exception as exc:
            safe_print(f"  [log] (tail unavailable: {exc})")
        safe_print(
            "  [hint] If Maestro said 'Flow file does not exist', fix runFlow paths from ATP subfolders "
            "(use ../../flows/ or ../../elements/ to reach repo root)."
        )
        tail = _read_log_tail_text(repo, suite_id, flow, dev, 80)
        if "7001" in tail and "Connection refused" in tail:
            print(
                "  [hint] localhost:7001 refused = Android driver IPC. "
                "run_one_flow_on_device retries once with --reinstall-driver. "
                "If it still fails: close Maestro Studio on the agent, stop other maestro.exe runs, then re-run.",
                flush=True,
            )
        return True
    print(f"  [OK] exit={ex} device={_dev_log(dev)}{dur_hint}", flush=True)
    log_lifecycle(repo, suite_id, WorkerState.COMPLETE, "flow ok", device=dev, flow=flow_base)
    return False


def _print_log_tail(repo: Path, suite_id: str, flow: Path, device_id: str) -> None:
    """Print last lines of a Maestro log; never raises (Unicode-safe on Windows)."""
    try:
        lp = _log_path(repo, suite_id, flow, device_id)
        safe_print(f"  [log] {lp} (last 45 lines):")
        if not lp.is_file():
            safe_print("    (no file)")
            return
        try:
            lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            safe_print(f"    (read error: {exc})")
            return
        for ln in lines[-45:]:
            safe_print(f"    {_sanitize_console_text(ln)}")
    except Exception as exc:
        safe_print(f"  [log] (tail print failed: {exc})")


def run_atp_folder_blocking(
    repo: Path,
    atp_subfolder: str,
    app_id: str,
    clear_state: str,
    maestro_cmd: str,
) -> int:
    configure_stdout_stderr_utf8()
    repo = repo.resolve()
    single_folder_mode = bool((atp_subfolder or "").strip())
    atp_root = repo / "ATP TestCase Flows"

    write_section(
        f"ATP TestCase Flows - {atp_subfolder.strip()}" if single_folder_mode else "ATP TestCase Flows (all folders)"
    )
    print(f"Repo root: {repo}", flush=True)
    print(f"ATP root:  {atp_root}", flush=True)
    if single_folder_mode:
        print(f"Subfolder: {atp_subfolder.strip()}", flush=True)
    print("ATP_JENKINS_ORCHESTRATOR_ACTIVE=1", flush=True)
    print(f"[ATP] orchestrator_rev={ORCHESTRATOR_REV}", flush=True)
    print(f"[ATP] orchestrator_file={Path(__file__).resolve()}", flush=True)
    print("[ATP] orchestrator=execution/atp_jenkins_orchestrator.py (blocking; no detached PS1)", flush=True)
    print(f"[ATP] git_branch={_atp_git_branch(repo)}", flush=True)
    if not _validate_execution_modules():
        return 1

    flows = discover_flows(repo, atp_subfolder)
    if not flows:
        if single_folder_mode:
            print(
                "[ATP] ERROR: no executable .yaml/.yml test files found for this stage "
                "(check folder mapping and ATP TestCase Flows layout)",
                flush=True,
            )
            return 1
        if atp_root.is_dir():
            print("[ATP] SKIP: no .yaml/.yml files under ATP TestCase Flows", flush=True)
        return 0

    if not (app_id or "").strip():
        print("ERROR: AppId required", flush=True)
        return 1
    clear_state = (clear_state or "true").strip()

    add_adb_from_env_to_path()
    from .subprocess_launch import log_subprocess_launch, resolve_adb_executable

    adb_exe = resolve_adb_executable()
    if adb_exe:
        for adb_args in (["start-server"], ["devices"]):
            adb_cmd = [adb_exe, *adb_args]
            log_subprocess_launch(adb_cmd, cwd=repo, shell=False, label="atp_orchestrator_adb")
            try:
                subprocess.run(
                    adb_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
                pass

    time.sleep(1)

    try:
        devices = merge_and_pick_devices_with_app_preflight(repo, app_id)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 1

    if not devices:
        print(
            "[ATP] SKIP: no devices available after app preflight "
            "(install APK or connect authorized device(s))",
            flush=True,
        )
        return 0

    print(f"Devices: {', '.join(_dev_log(d) for d in devices)}", flush=True)
    os.environ["ATP_ORCH_DEVICE_COUNT"] = str(len(devices))
    os.environ["ATP_ORCH_DEVICES"] = ",".join(devices)
    exec_mode = _device_execution_mode(len(devices))
    sched_mode = _scheduler_mode()
    # Resolve MAESTRO_HOME / capability before launcher (overrides stale Jenkins MAESTRO_HOME).
    if len(devices) >= 1:
        assert_native_parallel_ready(device_count=len(devices), devices=devices, repo=repo)
    try:
        maestro_launch = resolve_maestro_launcher(maestro_cmd)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 1
    print(f"Maestro: {maestro_launch}", flush=True)
    print(
        f"[ATP] device execution mode: {exec_mode} "
        f"(override: ATP_DEVICE_EXECUTION=sequential|parallel)",
        flush=True,
    )
    print(
        f"[ATP] scheduler mode: {sched_mode} "
        f"(override: ATP_SCHEDULER=dynamic|wave; wave = legacy flow barrier)",
        flush=True,
    )
    if exec_mode == "parallel" and len(devices) > 1:
        caps = detect_maestro_capabilities(device_count=len(devices), devices=devices)
        if caps.native_parallel_enabled:
            from .maestro_capabilities import log_native_parallel_runtime_config

            apply_native_parallel_env_defaults(device_count=len(devices), caps=caps)
            log_native_parallel_runtime_config(caps)
        stagger_env = (
            os.environ.get("ATP_PARALLEL_DEVICE_STAGGER_SEC") or _default_parallel_stagger_sec(len(devices))
        ).strip()
        gate_on = _handshake_gate_enabled(len(devices), exec_mode) and sched_mode == "wave"
        startup_gate_env = os.environ.get("ATP_MAESTRO_STARTUP_GATE", "0" if caps.native_parallel_enabled else "1")
        mutex_env = os.environ.get("ATP_MAESTRO_LEGACY_RUNTIME_MUTEX", "0" if caps.native_parallel_enabled else "1")
        print(f"[ATP] legacy_runtime_mutex={mutex_env}", flush=True)
        print(
            f"[ATP] parallel_device_stagger_sec={stagger_env} "
            f"(startup-only; index*N sec before worker begins; flows still parallel)",
            flush=True,
        )
        print(
            f"[ATP] maestro_startup_gate={startup_gate_env} "
            f"(0 = no init serialization; required for native parallel)",
            flush=True,
        )
        if sched_mode == "wave":
            print(
                f"[ATP] maestro_handshake_gate={'1' if gate_on else '0'} "
                f"(ATP_MAESTRO_HANDSHAKE_GATE; wave mode only)",
                flush=True,
            )
        print(
            "[ATP] parallel_paths: reports/<suite>/logs/<flow>_<device>.log "
            "status/<suite>__<flow>__<device>.txt maestro-debug/<flow>__<device>/",
            flush=True,
        )

    (repo / "status").mkdir(parents=True, exist_ok=True)

    cleanup_stale_device_leases(repo)

    labels: dict[str, str] = {}
    overall_failed = False

    use_dynamic = exec_mode == "parallel" and len(devices) > 1 and sched_mode == "dynamic"
    if use_dynamic:
        write_section("ATP dynamic worker-pool scheduler")
        print(
            f"[ATP] dynamic_pool flows={len(flows)} devices={len(devices)} "
            f"matrix_tasks={len(flows) * len(devices)}",
            flush=True,
        )
        overall_failed = _run_dynamic_worker_pool(
            repo=repo,
            atp_root=atp_root,
            flows=flows,
            devices=devices,
            app_id=app_id,
            clear_state=clear_state,
            maestro_launch=maestro_launch,
            labels=labels,
        )
    else:
        for flow in flows:
            folder_name = get_atp_folder_name(atp_root, flow)
            suite_id = get_atp_suite_id(folder_name)
            labels[suite_id] = folder_name
            flow_base = flow.stem
            write_section(f"ATP [{folder_name}] :: {flow_base} (suite={suite_id})")
            log_lifecycle(repo, suite_id, WorkerState.IDLE, "flow wave begin", flow=flow_base)

            outcomes = _run_flow_wave_on_devices(
                repo=repo,
                suite_id=suite_id,
                flow=flow,
                flow_base=flow_base,
                devices=devices,
                app_id=app_id,
                clear_state=clear_state,
                maestro_launch=maestro_launch,
            )
            for outcome in outcomes:
                if _report_device_outcome(repo, suite_id, flow, flow_base, outcome):
                    overall_failed = True

    bs = repo / "build-summary"
    bs.mkdir(parents=True, exist_ok=True)
    labels_path = bs / "atp_suite_labels.json"
    merge_atp_suite_labels_json(labels_path, labels, merge_existing=single_folder_mode)
    print(f"[ATP] Updated suite labels: {labels_path} (merge={single_folder_mode})", flush=True)

    if overall_failed:
        print("[ATP] Completed with failures.", flush=True)
        return 1
    print("[ATP] All flows passed.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_stdout_stderr_utf8()
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 4:
        print(
            "Usage: atp_jenkins_orchestrator.py <REPO_ROOT> <APP_PACKAGE> <CLEAR_STATE> <MAESTRO_CMD> [ATP_SUBFOLDER]",
            file=sys.stderr,
        )
        return 2
    repo = Path(argv[0]).resolve()
    app = argv[1]
    clear_s = argv[2]
    maestro_c = argv[3]
    sub = argv[4] if len(argv) > 4 else ""
    return run_atp_folder_blocking(repo, sub, app, clear_s, maestro_c)


if __name__ == "__main__":
    raise SystemExit(main())
