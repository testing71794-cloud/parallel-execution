#!/usr/bin/env python3
"""
Blocking ATP orchestration for Jenkins (Stack A entry for Maestro lifecycle).

Replaces the detached PowerShell Start-Process chain for ATP runs while
preserving scripts/run_one_flow_on_device.bat outputs (reports/, status/, CSV).

Does not modify Maestro YAML, Excel schema, AI logic, or report layouts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .device_lease import DeviceLease
from .maestro_runner import (
    WorkerState,
    log_lifecycle,
    post_run_validate,
    pre_maestro_cleanup,
    resolve_maestro_launcher,
    run_run_one_flow_device_bat,
)


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
    authorized = get_authorized_serials_from_adb()
    if not authorized:
        raise RuntimeError("No Android devices in state 'device'.")
    file_serials = read_detected_file_serials(repo)
    if not file_serials:
        return authorized
    picked = [s for s in file_serials if s in authorized]
    if not picked:
        print(
            f"[ATP] WARN: detected_devices.txt serial(s) not in current adb devices: {', '.join(file_serials)}",
            flush=True,
        )
        print(f"[ATP] WARN: falling back to all authorized device(s): {', '.join(authorized)}", flush=True)
        return authorized
    if len(picked) < len(file_serials):
        missing = [s for s in file_serials if s not in picked]
        print(f"[ATP] WARN: dropping stale serial(s) from detected_devices.txt: {', '.join(missing)}", flush=True)
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
    first = re.split(r"[\\/]", rest, 1)[0]
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

        for dev in devices:
            print(f"  device {dev}", flush=True)
            rd = repo / "reports" / suite_id
            (rd / "logs").mkdir(parents=True, exist_ok=True)
            (rd / "results").mkdir(parents=True, exist_ok=True)

            lease = DeviceLease.for_serial(repo, dev)
            log_lifecycle(repo, suite_id, WorkerState.ALLOCATED, "lease acquire", device=dev, flow=flow_base)
            lease.acquire()
            try:
                log_lifecycle(repo, suite_id, WorkerState.PREPARING, "preparing", device=dev, flow=flow_base)
                pre_maestro_cleanup(dev, suite_id, repo)
                log_lifecycle(repo, suite_id, WorkerState.RUNNING, "invoke run_one_flow_on_device.bat", device=dev)
                ex = run_run_one_flow_device_bat(
                    repo=repo,
                    suite_id=suite_id,
                    flow_path=flow,
                    device_id=dev,
                    app_id=app_id,
                    clear_state=clear_state,
                    maestro_launcher=maestro_launch,
                )
            finally:
                lease.release()
                log_lifecycle(repo, suite_id, WorkerState.IDLE, "lease released", device=dev)

            if ex != 0:
                overall_failed = True
                print(f"  [FAIL] exit={ex} device={dev} flow={flow_base}", flush=True)
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
            else:
                print(f"  [OK] exit={ex} device={dev}", flush=True)
                log_lifecycle(repo, suite_id, WorkerState.COMPLETE, "flow ok", device=dev, flow=flow_base)
            post_run_validate(repo, suite_id, ex, flow, dev)

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
