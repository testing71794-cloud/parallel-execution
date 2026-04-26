#!/usr/bin/env python3
"""
Parallel multi-device Maestro orchestration:
- One thread per device (flows sequential within the thread)
- JUnit + log per flow
- Immediate AI analysis on failure (optional)
- Incremental Excel append (thread-safe)
- Optional email after all devices complete

Does not modify Maestro YAML flows.

Maestro CLI: global --device before test (see docs/MAESTRO_OFFICIAL_REFERENCE.md).
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Sequence

# Repo root on path for `ai`, `excel`, `mailout`
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.run_ai_analysis import (  # noqa: E402
    analyze_flow_failure,
    extract_junit_summary,
    read_log_tail,
)
from excel.update_excel import append_result_row, finalize_workbook  # noqa: E402
from mailout.send_email import send_execution_report_email  # noqa: E402

logger = logging.getLogger("orch.parallel")


def _safe_device_dir(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name)


def list_adb_devices() -> list[str]:
    try:
        out = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.error("adb devices failed: %s", e)
        return []
    serials: list[str] = []
    for line in out.stdout.splitlines():
        m = re.match(r"^(\S+)\s+device\s*$", line.strip())
        if m:
            serials.append(m.group(1))
    return serials


def resolve_device_name(repo: Path, serial: str) -> str:
    script = repo / "scripts" / "resolve_device_name.py"
    if not script.is_file():
        return serial
    try:
        r = subprocess.run(
            [sys.executable, str(script), serial],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        name = (r.stdout or "").strip().splitlines()
        if name:
            return name[0].strip() or serial
    except Exception as e:
        logger.debug("resolve_device_name: %s", e)
    return serial


def read_flow_paths(repo: Path, flows_file: Path) -> list[Path]:
    if not flows_file.is_file():
        raise FileNotFoundError(f"Flows file not found: {flows_file}")
    paths: list[Path] = []
    for line in flows_file.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        p = (repo / s).resolve() if not Path(s).is_absolute() else Path(s)
        paths.append(p)
    return paths


def build_maestro_cmd(
    maestro: Path | str,
    device_id: str,
    flow_path: Path,
    config_path: Path,
    junit_out: Path,
) -> list[str]:
    """Build argv for subprocess; use cmd /c on Windows for .bat/.cmd."""
    maestro_s = str(maestro)
    parts = [
        "--device",
        device_id,
        "test",
        str(flow_path),
        "--config",
        str(config_path),
        "--format",
        "junit",
        "--output",
        str(junit_out),
    ]
    lower = maestro_s.lower()
    if lower.endswith(".bat") or lower.endswith(".cmd"):
        return ["cmd", "/c", maestro_s, *parts]
    return [maestro_s, *parts]


def run_maestro_flow(
    maestro: Path,
    device_id: str,
    flow_path: Path,
    config_path: Path,
    junit_out: Path,
    log_path: Path,
    repo: Path,
) -> int:
    junit_out.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_maestro_cmd(maestro, device_id, flow_path, config_path, junit_out)
    logger.info("Device %s flow %s", device_id, flow_path.name)
    logger.debug("CMD %s", cmd)
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_f:
            proc = subprocess.run(
                cmd,
                cwd=str(repo.resolve()),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=3600,
                check=False,
                shell=False,
            )
        return int(proc.returncode)
    except subprocess.TimeoutExpired:
        log_path.write_text("Maestro subprocess timeout\n", encoding="utf-8")
        return 124
    except Exception as e:
        log_path.write_text(f"Maestro launch error: {e}\n", encoding="utf-8")
        return 1


def device_worker(
    device_id: str,
    flows: Sequence[Path],
    *,
    repo: Path,
    maestro: Path,
    config_path: Path,
    excel_path: Path,
    excel_lock: threading.Lock,
    use_ai: bool,
) -> None:
    log_base = repo / "logs" / _safe_device_dir(device_id)
    log_base.mkdir(parents=True, exist_ok=True)
    device_name = resolve_device_name(repo, device_id)

    for flow_path in flows:
        stem = _safe_device_dir(flow_path.stem)
        junit_path = log_base / f"{stem}_junit.xml"
        log_path = log_base / f"{stem}.log"
        try:
            flow_display = str(flow_path.resolve().relative_to(repo.resolve()))
        except ValueError:
            flow_display = flow_path.name

        t0 = time.perf_counter()
        try:
            rc = run_maestro_flow(
                maestro,
                device_id,
                flow_path.resolve(),
                config_path.resolve(),
                junit_path,
                log_path,
                repo,
            )
        except Exception as e:
            logger.exception("Unexpected error running Maestro: %s", e)
            rc = 1

        duration_s = time.perf_counter() - t0
        duration_str = f"{duration_s:.2f}s"

        status, test_name, failure_msg = extract_junit_summary(junit_path, flow_display)
        if rc != 0 and status == "PASS":
            status = "FAIL"
            failure_msg = (failure_msg or "") + f"\nMaestro exit code: {rc}"
        if rc != 0 and status == "UNKNOWN":
            failure_msg = (failure_msg or "") + f"Maestro exit code: {rc}"

        ai_text = ""
        if use_ai and status not in ("PASS",):
            excerpt = read_log_tail(log_path)
            try:
                ai_text = analyze_flow_failure(
                    test_name=test_name,
                    status=status,
                    failure_message=failure_msg,
                    log_excerpt=excerpt,
                )
            except Exception as e:
                logger.error("AI pipeline error: %s", e)
                ai_text = "AI Analysis Failed"

        row = {
            "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "Device Name": device_name,
            "Flow Name": flow_display,
            "Test Status": status,
            "Failure Message": failure_msg[:8000] if failure_msg else "",
            "AI Analysis": ai_text,
            "Duration": duration_str,
        }
        try:
            append_result_row(excel_path, row, file_lock=excel_lock)
        except Exception as e:
            logger.error("Excel append failed: %s", e)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel device orchestration for Maestro flows")
    p.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: parent of execution/)",
    )
    p.add_argument(
        "--flows-file",
        type=Path,
        default=REPO_ROOT / "execution" / "default_flows.txt",
        help="Text file: one flow path per line, relative to repo root",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=REPO_ROOT / "config.yaml",
        help="Maestro workspace config path",
    )
    p.add_argument(
        "--maestro",
        type=Path,
        default=Path("maestro.bat"),
        help="Maestro launcher (e.g. maestro.bat or full path)",
    )
    p.add_argument(
        "--excel-out",
        type=Path,
        default=REPO_ROOT / "build-summary" / "final_execution_report.xlsx",
        help="Incremental Excel report path",
    )
    p.add_argument("--no-ai", action="store_true", help="Skip OpenRouter analysis")
    p.add_argument(
        "--send-email",
        action="store_true",
        help="Send email after run (requires SMTP env vars)",
    )
    p.add_argument(
        "--devices",
        nargs="*",
        default=None,
        help="ADB serials (default: all connected devices)",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.DEBUG if _orch_debug() else logging.INFO,
        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
    )
    args = parse_args()
    repo = args.repo_root.resolve()
    flows = read_flow_paths(repo, args.flows_file.resolve())
    if not flows:
        logger.error("No flows to run (check %s)", args.flows_file)
        return 1

    devices = args.devices if args.devices else list_adb_devices()
    if not devices:
        logger.error("No Android devices in 'adb devices'")
        return 1

    config_path = args.config if args.config.is_absolute() else repo / args.config
    maestro_arg = args.maestro if args.maestro.is_absolute() else Path(args.maestro)
    maestro = maestro_arg
    if not maestro.is_absolute():
        found = shutil.which(str(maestro_arg))
        if found:
            maestro = Path(found)
    excel_path = args.excel_out if args.excel_out.is_absolute() else repo / args.excel_out
    excel_path.parent.mkdir(parents=True, exist_ok=True)

    excel_lock = threading.Lock()
    use_ai = not args.no_ai

    logger.info("Devices: %s", devices)
    logger.info("Flows (%s): %s", len(flows), [f.name for f in flows])

    with ThreadPoolExecutor(max_workers=len(devices), thread_name_prefix="device") as ex:
        futs = [
            ex.submit(
                device_worker,
                d,
                flows,
                repo=repo,
                maestro=maestro,
                config_path=config_path,
                excel_path=excel_path,
                excel_lock=excel_lock,
                use_ai=use_ai,
            )
            for d in devices
        ]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                logger.error("Device worker failed: %s", e)

    try:
        finalize_workbook(excel_path, file_lock=excel_lock)
    except Exception as e:
        logger.error("Finalize Excel: %s", e)

    if args.send_email:
        send_execution_report_email(excel_path)

    logger.info("Done. Report: %s", excel_path)
    return 0


def _orch_debug() -> bool:
    return os.environ.get("ORCH_DEBUG", "").strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":
    raise SystemExit(main())
