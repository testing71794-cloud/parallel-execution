#!/usr/bin/env python3
"""
Blocking ATP orchestration for Jenkins (Stack A entry for Maestro lifecycle).

Replaces the detached PowerShell Start-Process chain for ATP runs while
preserving scripts/run_one_flow_on_device.bat outputs (reports/, status/, CSV).

Does not modify Maestro YAML, Excel schema, AI logic, or report layouts.

Flow-level synchronized multi-device execution (default when 2+ devices):
  Flow 1 on all devices in parallel -> barrier -> Flow 2 on all devices in parallel -> ...
  Override: ATP_DEVICE_EXECUTION=sequential for legacy one-device-at-a-time scheduling.
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

from .device_lease import DeviceLease
from .maestro_runner import (
    WorkerState,
    _status_file_path,
    log_lifecycle,
    post_run_validate,
    pre_maestro_cleanup,
    resolve_maestro_launcher,
    run_run_one_flow_device_bat,
)
from .flow_timing import read_status_fields

# Bump when orchestration semantics change (visible in Jenkins console).
ORCHESTRATOR_REV = "2026-05-parallel-wave-2"


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
    adb = shutil.which("adb")
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


def merge_and_pick_devices(repo: Path) -> list[str]:
    """Live ``adb devices`` is authoritative; detected_devices.txt may filter but never shrink below adb."""
    authorized = get_authorized_serials_from_adb()
    if not authorized:
        raise RuntimeError("No Android devices in state 'device'.")
    file_serials = read_detected_file_serials(repo)
    print(
        f"[ATP] devices adb={len(authorized)} [{', '.join(authorized)}] "
        f"detected_file={len(file_serials)} [{', '.join(file_serials) if file_serials else '-'}]",
        flush=True,
    )
    if not file_serials:
        return list(authorized)
    picked = [s for s in file_serials if s in authorized]
    if not picked:
        print(
            f"[ATP] WARN: detected_devices.txt serial(s) not in current adb devices: {', '.join(file_serials)}",
            flush=True,
        )
        print(f"[ATP] WARN: falling back to all authorized device(s): {', '.join(authorized)}", flush=True)
        return list(authorized)
    if len(picked) < len(file_serials):
        missing = [s for s in file_serials if s not in picked]
        print(f"[ATP] WARN: dropping stale serial(s) from detected_devices.txt: {', '.join(missing)}", flush=True)
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
    if not atp_root.is_dir():
        print("[ATP] SKIP: folder not found - ATP TestCase Flows", flush=True)
        return []
    sub = (atp_subfolder or "").strip()
    if sub:
        folder_root = atp_root / sub
        if not folder_root.is_dir():
            print(f"[ATP] SKIP: subfolder not found: {sub}", flush=True)
            return []
        roots = [folder_root]
    else:
        roots = [atp_root]
    flows: list[Path] = []
    for root in roots:
        for p in sorted(root.rglob("*"), key=lambda x: str(x).lower()):
            if p.is_file() and p.suffix.lower() in (".yaml", ".yml"):
                flows.append(p)
    return flows


def write_section(title: str) -> None:
    print("", flush=True)
    print("=====================================", flush=True)
    print(title, flush=True)
    print("=====================================", flush=True)


def _safe_flow_stem(flow: Path) -> str:
    return re.sub(r"\s+", "_", flow.stem)


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


def _parallel_launch_stagger_sec(launch_index: int) -> float:
    """Stagger Maestro driver handshake on one host to reduce adb TcpForwarder races (Windows)."""
    if launch_index <= 0:
        return 0.0
    raw = (os.environ.get("ATP_PARALLEL_DEVICE_STAGGER_SEC") or "").strip()
    if not raw:
        raw = "3" if os.name == "nt" else "0"
    try:
        return max(0.0, float(raw)) * launch_index
    except ValueError:
        return 0.0


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
    device_id: str,
    app_id: str,
    clear_state: str,
    maestro_launch: Path,
    allow_maestro_kill: bool,
    launch_index: int = 0,
) -> _DeviceFlowOutcome:
    """One device in a flow wave: lease, bat, status/log per device (isolated paths)."""
    stagger = _parallel_launch_stagger_sec(launch_index)
    if stagger > 0:
        print(
            f"[ATP] parallel_stagger device={device_id} flow={flow_base} sleep_sec={stagger:.1f}",
            flush=True,
        )
        time.sleep(stagger)
    rd = repo / "reports" / suite_id
    (rd / "logs").mkdir(parents=True, exist_ok=True)
    (rd / "results").mkdir(parents=True, exist_ok=True)

    lease = DeviceLease.for_serial(repo, device_id)
    log_lifecycle(
        repo, suite_id, WorkerState.ALLOCATED, "lease acquire", device=device_id, flow=flow_base
    )
    lease.acquire()
    exit_code = 1
    t0 = time.time()
    print(
        f"[ATP] device_run_start device={device_id} flow={flow_base} "
        f"thread={threading.current_thread().name} ts={t0:.3f}",
        flush=True,
    )
    try:
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
        )
    finally:
        lease.release()
        log_lifecycle(repo, suite_id, WorkerState.IDLE, "lease released", device=device_id)
        print(
            f"[ATP] device_run_end device={device_id} flow={flow_base} exit={exit_code} "
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
            f"  [ATP] flow wave parallel: {flow_base} on {len(devices)} device(s): {', '.join(devices)}",
            flush=True,
        )
        outcomes: list[_DeviceFlowOutcome] = []
        with ThreadPoolExecutor(max_workers=len(devices), thread_name_prefix="atp-flow") as pool:
            for dev in devices:
                print(
                    f"  [ATP] threadpool_submit device={dev} flow={flow_base} ts={time.time():.3f}",
                    flush=True,
                )
            futures = {
                pool.submit(
                    _execute_flow_on_device,
                    repo=repo,
                    suite_id=suite_id,
                    flow=flow,
                    flow_base=flow_base,
                    device_id=dev,
                    app_id=app_id,
                    clear_state=clear_state,
                    maestro_launch=maestro_launch,
                    allow_maestro_kill=allow_maestro_kill,
                    launch_index=idx,
                ): dev
                for idx, dev in enumerate(devices)
            }
            for fut in as_completed(futures):
                try:
                    outcomes.append(fut.result())
                except Exception as exc:
                    dev = futures[fut]
                    print(f"  [FAIL] device={dev} flow={flow_base} orchestrator error: {exc}", flush=True)
                    outcomes.append(_DeviceFlowOutcome(device_id=dev, exit_code=1))
        order = {d: i for i, d in enumerate(devices)}
        outcomes.sort(key=lambda o: order.get(o.device_id, 999))
        print(
            f"[ATP] flow_wave_barrier_done flow={flow_base} mode=parallel "
            f"elapsed_sec={time.time() - wave_t0:.1f}",
            flush=True,
        )
        return outcomes

    print(f"  [ATP] flow wave sequential: {flow_base}", flush=True)
    seq_outcomes: list[_DeviceFlowOutcome] = []
    for dev in devices:
        print(f"  device {dev}", flush=True)
        seq_outcomes.append(
            _execute_flow_on_device(
                repo=repo,
                suite_id=suite_id,
                flow=flow,
                flow_base=flow_base,
                device_id=dev,
                app_id=app_id,
                clear_state=clear_state,
                maestro_launch=maestro_launch,
                allow_maestro_kill=True,
            )
        )
    print(
        f"[ATP] flow_wave_barrier_done flow={flow_base} mode=sequential "
        f"elapsed_sec={time.time() - wave_t0:.1f}",
        flush=True,
    )
    return seq_outcomes


def _report_device_outcome(
    repo: Path,
    suite_id: str,
    flow: Path,
    flow_base: str,
    outcome: _DeviceFlowOutcome,
) -> bool:
    """Print console result for one device; return True if failed."""
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
    if ex != 0:
        print(f"  [FAIL] exit={ex} device={dev} flow={flow_base}{dur_hint}", flush=True)
        _print_log_tail(repo, suite_id, flow, dev)
        print(
            "  [hint] If Maestro said 'Flow file does not exist', fix runFlow paths from ATP subfolders "
            "(use ../../flows/ or ../../elements/ to reach repo root).",
            flush=True,
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
    print(f"  [OK] exit={ex} device={dev}{dur_hint}", flush=True)
    log_lifecycle(repo, suite_id, WorkerState.COMPLETE, "flow ok", device=dev, flow=flow_base)
    return False


def _print_log_tail(repo: Path, suite_id: str, flow: Path, device_id: str) -> None:
    lp = _log_path(repo, suite_id, flow, device_id)
    print(f"  [log] {lp} (last 45 lines):", flush=True)
    if not lp.is_file():
        print("    (no file)", flush=True)
        return
    try:
        lines = lp.read_text(encoding="utf-8", errors="replace").splitlines()
        for ln in lines[-45:]:
            print(f"    {ln}", flush=True)
    except OSError as e:
        print(f"    (read error: {e})", flush=True)


def run_atp_folder_blocking(
    repo: Path,
    atp_subfolder: str,
    app_id: str,
    clear_state: str,
    maestro_cmd: str,
) -> int:
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

    flows = discover_flows(repo, atp_subfolder)
    if not flows:
        if atp_root.is_dir():
            print("[ATP] SKIP: no .yaml/.yml files under ATP TestCase Flows", flush=True)
        return 0

    if not (app_id or "").strip():
        print("ERROR: AppId required", flush=True)
        return 1
    clear_state = (clear_state or "true").strip()

    add_adb_from_env_to_path()
    try:
        subprocess.run(["adb", "start-server"], capture_output=True, text=True, timeout=60, check=False)
        subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=60, check=False)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    time.sleep(1)

    try:
        devices = merge_and_pick_devices(repo)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 1

    print(f"Devices: {', '.join(devices)}", flush=True)
    try:
        maestro_launch = resolve_maestro_launcher(maestro_cmd)
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return 1
    print(f"Maestro: {maestro_launch}", flush=True)
    exec_mode = _device_execution_mode(len(devices))
    print(
        f"[ATP] device execution mode: {exec_mode} "
        f"(override: ATP_DEVICE_EXECUTION=sequential|parallel)",
        flush=True,
    )
    if exec_mode == "parallel" and len(devices) > 1:
        stagger_default = "3" if os.name == "nt" else "0"
        stagger_env = (os.environ.get("ATP_PARALLEL_DEVICE_STAGGER_SEC") or stagger_default).strip()
        print(
            f"[ATP] parallel_device_stagger_sec={stagger_env} "
            f"(per-device index delay before Maestro; set 0 for simultaneous handshake)",
            flush=True,
        )

    (repo / "status").mkdir(parents=True, exist_ok=True)

    labels: dict[str, str] = {}
    overall_failed = False

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
