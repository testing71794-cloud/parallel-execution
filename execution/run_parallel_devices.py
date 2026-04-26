#!/usr/bin/env python3
"""
Parallel multi-device Maestro orchestration (production).

Before anything else: auto cleanup (logs, reports, build-summary, …) unless --no-clean.
Per device: parallel thread. Per device: flows run sequentially.

Per flow artifacts (no reuse from prior runs):
  logs/<device_serial>/<flow_stem>/junit.xml
  logs/<device_serial>/<flow_stem>/maestro.log

Excel: fresh file each run (prime after cleanup), columns include AI Analysis, live Timestamp.

Does not modify Maestro YAML.

CLI: maestro --device <serial> test <flow> --config config.yaml --format junit --output <junit.xml>
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.run_ai_analysis import (  # noqa: E402
    analyze_flow_failure,
    extract_junit_summary,
    read_log_tail,
)
from excel.update_excel import append_result_row, finalize_workbook, prime_workbook  # noqa: E402
from execution.cleanup_previous_run import cleanup_for_new_run  # noqa: E402
from mailout.send_email import send_execution_report_email  # noqa: E402

logger = logging.getLogger("orch.parallel")


def _safe_segment(name: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", name)


def suite_and_flow(flow_path: Path, repo: Path) -> tuple[str, str]:
    """Suite = first path segment under repo (e.g. Non printing flows); Flow = yaml file name."""
    try:
        rel = flow_path.resolve().relative_to(repo.resolve())
        parts = rel.parts
        if len(parts) >= 2:
            return parts[0], parts[-1]
        return "", rel.name
    except ValueError:
        return "", flow_path.name


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
    flow_run_dir = junit_out.parent
    flow_run_dir.mkdir(parents=True, exist_ok=True)

    if junit_out.is_file():
        try:
            junit_out.unlink()
        except OSError as e:
            logger.warning("Could not remove stale junit.xml %s: %s", junit_out, e)

    cmd = build_maestro_cmd(maestro, device_id, flow_path, config_path, junit_out)
    logger.info("Flow started | %s | %s", flow_path.name, device_id)
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
        code = int(proc.returncode)
        logger.info("Flow completed | %s | %s | exit=%s", flow_path.name, device_id, code)
        return code
    except subprocess.TimeoutExpired:
        log_path.write_text("Maestro subprocess timeout\n", encoding="utf-8")
        logger.error("Flow timeout | %s | %s", flow_path.name, device_id)
        return 124
    except Exception as e:
        log_path.write_text(f"Maestro launch error: {e}\n", encoding="utf-8")
        logger.error("Flow launch error | %s | %s", device_id, e)
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
    outcome_lock: threading.Lock,
    shared_outcomes: list[str],
) -> None:
    device_name = resolve_device_name(repo, device_id)
    logger.info("Device %s detected (%s)", device_id, device_name)
    print(f"[INFO] Device {device_id} detected ({device_name})", flush=True)

    log_base = repo / "logs" / _safe_segment(device_id)

    for flow_path in flows:
        stem = _safe_segment(flow_path.stem)
        flow_run_dir = log_base / stem
        flow_run_dir.mkdir(parents=True, exist_ok=True)
        junit_path = flow_run_dir / "junit.xml"
        log_path = flow_run_dir / "maestro.log"

        suite, flow_file = suite_and_flow(flow_path, repo)
        try:
            flow_rel = str(flow_path.resolve().relative_to(repo.resolve()))
        except ValueError:
            flow_rel = flow_path.name

        print(f"[INFO] Running {flow_file} on {device_id}", flush=True)
        logger.info("Running %s on device %s", flow_rel, device_id)

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
            logger.exception("Unexpected Maestro error: %s", e)
            rc = 1

        status, test_name, failure_msg = extract_junit_summary(junit_path, flow_rel)
        if rc != 0 and status == "PASS":
            status = "FAIL"
            failure_msg = (failure_msg or "") + f"\nMaestro exit code: {rc}"
        if rc != 0 and status == "UNKNOWN":
            failure_msg = (failure_msg or "") + f"Maestro exit code: {rc}"

        ai_text = ""
        if status.upper() == "PASS":
            ai_text = "N/A — passed"
        elif use_ai:
            logger.info("AI triggered | %s | %s | status=%s", flow_file, device_id, status)
            print(f"[INFO] AI triggered | {flow_file} | {device_id}", flush=True)
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
            if not (ai_text or "").strip():
                ai_text = "AI Analysis Failed"
            logger.info("AI result received | %s | %s", flow_file, device_id)
            print(f"[INFO] AI result received | {flow_file} | {device_id}", flush=True)
        else:
            ai_text = "AI disabled (--no-ai)"

        print(f"[INFO] AI Result ({device_id} / {flow_file}): {ai_text[:200]!s}", flush=True)

        ts = datetime.now().replace(microsecond=0).isoformat()
        row = {
            "Timestamp": ts,
            "Suite": suite,
            "Flow": flow_file,
            "Device": f"{device_name} ({device_id})",
            "Status": status,
            "Exit Code": str(rc),
            "Log Path": str(log_path.resolve()),
            "AI Analysis": ai_text,
        }
        try:
            append_result_row(excel_path, row, file_lock=excel_lock)
            logger.info("Excel updated | %s | %s", flow_file, device_id)
            print(f"[INFO] Excel updated | {flow_file} | {device_id}", flush=True)
        except Exception as e:
            logger.error("Excel append failed: %s", e)

        with outcome_lock:
            shared_outcomes.append(status.upper())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel device orchestration for Maestro flows")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    p.add_argument(
        "--flows-file",
        type=Path,
        default=REPO_ROOT / "execution" / "default_flows.txt",
    )
    p.add_argument("--config", type=Path, default=REPO_ROOT / "config.yaml")
    p.add_argument("--maestro", type=Path, default=Path("maestro.bat"))
    p.add_argument(
        "--excel-out",
        type=Path,
        default=REPO_ROOT / "final_execution_report.xlsx",
    )
    p.add_argument("--no-ai", action="store_true")
    p.add_argument("--send-email", action="store_true")
    p.add_argument("--devices", nargs="*", default=None)
    p.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip auto-delete of logs, reports, build-summary, etc.",
    )
    p.add_argument(
        "--no-prime",
        action="store_true",
        help="Do not recreate Excel; append only (e.g. printing suite after non-printing in same job).",
    )
    return p.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.DEBUG if _orch_debug() else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    args = parse_args()
    repo = args.repo_root.resolve()
    excel_path = args.excel_out if args.excel_out.is_absolute() else repo / args.excel_out

    excel_lock = threading.Lock()
    outcome_lock = threading.Lock()
    shared_outcomes: list[str] = []
    use_ai = not args.no_ai

    if not args.no_clean:
        cleanup_for_new_run(repo)
    else:
        logger.warning("Skipping pre-run cleanup (--no-clean)")

    # Prime Excel before flow/device checks so Jenkins email step always has a file to attach
    # when the job fails early (no devices, bad flows file, etc.).
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_prime:
        prime_workbook(excel_path, file_lock=excel_lock)
    elif not excel_path.is_file():
        logger.warning("Excel missing with --no-prime; priming new workbook")
        prime_workbook(excel_path, file_lock=excel_lock)

    try:
        flows = read_flow_paths(repo, args.flows_file.resolve())
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if not flows:
        logger.error("No flows to run (check %s)", args.flows_file)
        return 1

    devices = args.devices if args.devices else list_adb_devices()
    if not devices:
        logger.error("No Android devices in 'adb devices'")
        return 1

    for d in devices:
        logger.info("Device %s detected", d)
        print(f"[INFO] Device {d} detected", flush=True)

    config_path = args.config if args.config.is_absolute() else repo / args.config
    maestro_arg = args.maestro if args.maestro.is_absolute() else Path(args.maestro)
    maestro = maestro_arg
    if not maestro.is_absolute():
        found = shutil.which(str(maestro_arg))
        if found:
            maestro = Path(found)

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
                outcome_lock=outcome_lock,
                shared_outcomes=shared_outcomes,
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
    print(f"[INFO] Final Excel: {excel_path}", flush=True)

    if shared_outcomes and any(s != "PASS" for s in shared_outcomes):
        logger.warning("Run finished with one or more non-PASS results (see Excel)")
        return 1
    return 0


def _orch_debug() -> bool:
    return os.environ.get("ORCH_DEBUG", "").strip().lower() in ("1", "true", "yes")


if __name__ == "__main__":
    raise SystemExit(main())
