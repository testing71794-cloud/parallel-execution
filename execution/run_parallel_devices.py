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


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _parse_java_major(version_text: str) -> int:
    """
    Parse Java major from `java -version` output.
    Handles `17.0.8`, `21.0.2`, and legacy `1.8.0_...`.
    """
    m = re.search(r'version\s+"([^"]+)"', version_text)
    if not m:
        return 0
    raw = m.group(1).strip()
    if raw.startswith("1."):
        parts = raw.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            return int(parts[1])
        return 0
    head = raw.split(".", 1)[0]
    return int(head) if head.isdigit() else 0


def _java_home_from_exe(java_exe: Path) -> Path | None:
    # .../bin/java(.exe) -> JAVA_HOME
    parent = java_exe.parent
    if parent.name.lower() == "bin":
        home = parent.parent
        if home.is_dir():
            return home
    return None


def _candidate_java_exes() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()

    def add(p: Path | None) -> None:
        if not p:
            return
        try:
            rp = str(p.resolve())
        except OSError:
            return
        if rp in seen:
            return
        seen.add(rp)
        out.append(Path(rp))

    # Highest priority: explicit envs
    for env_name in ("MAESTRO_JAVA_HOME", "JAVA_HOME"):
        root = os.environ.get(env_name, "").strip().strip('"')
        if root:
            add(Path(root) / "bin" / ("java.exe" if os.name == "nt" else "java"))

    # PATH
    on_path = shutil.which("java")
    if on_path:
        add(Path(on_path))

    # Windows where java (captures multiple installed JDKs/JREs)
    if os.name == "nt":
        try:
            proc = subprocess.run(
                ["cmd", "/c", "where", "java"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip().strip('"')
                if line:
                    add(Path(line))
        except OSError:
            pass

    return [p for p in out if p.is_file()]


def resolve_maestro_java_home() -> Path | None:
    """
    Choose JAVA_HOME for Maestro. Prefer Java 17 specifically, else any 17+.
    """
    java17: Path | None = None
    java17plus: Path | None = None
    for exe in _candidate_java_exes():
        try:
            proc = subprocess.run(
                [str(exe), "-version"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        merged = (proc.stderr or "") + "\n" + (proc.stdout or "")
        major = _parse_java_major(merged)
        home = _java_home_from_exe(exe)
        if not home:
            continue
        if major == 17 and not java17:
            java17 = home
        if major >= 17 and not java17plus:
            java17plus = home
    return java17 or java17plus


def _adb_filename() -> str:
    return "adb.exe" if os.name == "nt" else "adb"


def _add_adb_candidate(seen: set[str], out: list[str], candidate: str | None) -> None:
    if not candidate:
        return
    s = str(candidate).strip().strip('"')
    if not s:
        return
    p = Path(s)
    if p.is_dir():
        exe = p / _adb_filename()
        if exe.is_file():
            s = str(exe.resolve())
    elif p.is_file():
        s = str(p.resolve())
    if s not in seen:
        seen.add(s)
        out.append(s)


def _adb_candidates_from_where_windows() -> list[str]:
    out: list[str] = []
    try:
        proc = subprocess.run(
            ["cmd", "/c", "where", "adb"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return out
    for line in (proc.stdout or "").splitlines():
        line = line.strip().strip('"')
        if line and Path(line).is_file():
            out.append(str(Path(line).resolve()))
    return out


def iter_adb_candidates(cli_adb: str | None = None) -> list[str]:
    """
    Ordered adb.exe paths to try (first working wins in list_adb_devices).
    Jenkins/interactive CMD often differ on PATH; we also probe ANDROID_HOME and `where adb` on Windows.
    """
    seen_set: set[str] = set()
    out: list[str] = []

    if cli_adb:
        _add_adb_candidate(seen_set, out, cli_adb)

    for env in ("ADB", "ADB_PATH"):
        _add_adb_candidate(seen_set, out, os.environ.get(env, "").strip().strip('"'))

    w = shutil.which("adb")
    _add_adb_candidate(seen_set, out, w)

    name = _adb_filename()
    for root_env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if root:
            _add_adb_candidate(seen_set, out, str(Path(root) / "platform-tools" / name))

    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            _add_adb_candidate(
                seen_set,
                out,
                str(Path(local) / "Android" / "Sdk" / "platform-tools" / name),
            )
        for p in _adb_candidates_from_where_windows():
            _add_adb_candidate(seen_set, out, p)

    return out


def _enriched_env_for_adb() -> dict[str, str]:
    """Prepend SDK platform-tools to PATH so adb and its DLLs resolve like an interactive shell."""
    env = os.environ.copy()
    extra_prefix: list[str] = []
    for root_env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if root:
            pt = str(Path(root) / "platform-tools")
            if Path(pt).is_dir():
                extra_prefix.append(pt)
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            pt = str(Path(local) / "Android" / "Sdk" / "platform-tools")
            if Path(pt).is_dir():
                extra_prefix.append(pt)
    if extra_prefix:
        old = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(extra_prefix) + os.pathsep + old
    return env


def _run_adb(adb_exe: str, args: Sequence[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [adb_exe, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=_enriched_env_for_adb(),
    )


def maybe_disable_device_autofill(adb_exe: str, device_id: str) -> str:
    """
    Best-effort pre-test protection against Google/Samsung autofill popups.
    Returns previously configured autofill service (or empty/unknown sentinel).
    Never raises.
    """
    original = "unknown"
    try:
        got = _run_adb(adb_exe, ["-s", device_id, "shell", "settings", "get", "secure", "autofill_service"])
        text = (got.stdout or "").strip()
        if text:
            original = text
    except Exception as e:
        logger.warning("[WARN] Device %s: failed reading autofill_service: %s", device_id, e)

    logger.info("[INFO] Device %s autofill_service before change: %s", device_id, original)
    print(f"[INFO] Device {device_id} autofill_service before change: {original}", flush=True)

    try:
        put = _run_adb(adb_exe, ["-s", device_id, "shell", "settings", "put", "secure", "autofill_service", "null"])
        if put.returncode == 0:
            logger.info("[INFO] Device %s autofill disabled (autofill_service=null)", device_id)
            print(f"[INFO] Device {device_id} autofill disabled (autofill_service=null)", flush=True)
        else:
            logger.warning(
                "[WARN] Device %s: could not disable autofill_service (rc=%s): %s",
                device_id,
                put.returncode,
                (put.stderr or put.stdout or "").strip(),
            )
    except Exception as e:
        logger.warning("[WARN] Device %s: autofill disable command failed: %s", device_id, e)

    # Samsung Pass related package names vary by OS version; disable best-effort only.
    samsung_pkgs = (
        "com.samsung.android.samsungpassautofill",
        "com.samsung.android.authfw",
    )
    for pkg in samsung_pkgs:
        try:
            cmd = _run_adb(
                adb_exe,
                ["-s", device_id, "shell", "cmd", "package", "disable-user", "--user", "0", pkg],
                timeout=45,
            )
            if cmd.returncode == 0:
                logger.info("[INFO] Device %s Samsung autofill package disabled: %s", device_id, pkg)
            else:
                logger.warning(
                    "[WARN] Device %s Samsung package not disabled (supported/installed?) %s rc=%s",
                    device_id,
                    pkg,
                    cmd.returncode,
                )
        except Exception as e:
            logger.warning("[WARN] Device %s: Samsung autofill disable failed for %s: %s", device_id, pkg, e)

    return original


def maybe_restore_device_autofill(adb_exe: str, device_id: str, original: str) -> None:
    if not original or original.lower() == "unknown":
        logger.warning("[WARN] Device %s: no saved autofill_service to restore", device_id)
        return
    value = "null" if original.lower() == "null" else original
    try:
        rst = _run_adb(adb_exe, ["-s", device_id, "shell", "settings", "put", "secure", "autofill_service", value])
        if rst.returncode == 0:
            logger.info("[INFO] Device %s autofill_service restored to: %s", device_id, value)
            print(f"[INFO] Device {device_id} autofill_service restored", flush=True)
        else:
            logger.warning(
                "[WARN] Device %s: failed to restore autofill_service rc=%s",
                device_id,
                rst.returncode,
            )
    except Exception as e:
        logger.warning("[WARN] Device %s: autofill restore command failed: %s", device_id, e)


def select_working_adb(cli_adb: str | None = None) -> tuple[str | None, subprocess.CompletedProcess[str] | None]:
    candidates = iter_adb_candidates(cli_adb)
    if not candidates:
        return None, None
    env = _enriched_env_for_adb()
    for adb_exe in candidates:
        logger.info("Trying adb: %s", adb_exe)
        try:
            proc = subprocess.run(
                [adb_exe, "devices"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env=env,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
            logger.warning("adb not runnable (%s): %s", adb_exe, e)
            continue
        logger.info("Using adb: %s", adb_exe)
        return adb_exe, proc
    return None, None


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


def list_adb_devices(*, cli_adb: str | None = None) -> list[str]:
    adb_exe, out = select_working_adb(cli_adb)
    if not adb_exe or out is None:
        logger.error(
            "adb not found. Install platform-tools, set ANDROID_HOME to the SDK root, "
            "add platform-tools to PATH, pass --adb, or set ADB to the full path of adb.exe."
        )
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
        run_env = os.environ.copy()
        # Force Maestro onto compatible Java in Jenkins hosts with mixed JRE/JDK installs.
        chosen_java = resolve_maestro_java_home()
        if chosen_java:
            run_env["MAESTRO_JAVA_HOME"] = str(chosen_java)
            run_env["JAVA_HOME"] = str(chosen_java)
            logger.info("Using JAVA_HOME for Maestro: %s", chosen_java)
        else:
            logger.warning("No Java 17+ detected for Maestro; using current process env")
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_f:
            proc = subprocess.run(
                cmd,
                cwd=str(repo.resolve()),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=3600,
                check=False,
                shell=False,
                env=run_env,
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
    adb_exe: str,
    restore_autofill: bool,
    outcome_lock: threading.Lock,
    shared_outcomes: list[str],
) -> None:
    device_name = resolve_device_name(repo, device_id)
    logger.info("Device %s detected (%s)", device_id, device_name)
    print(f"[INFO] Device {device_id} detected ({device_name})", flush=True)

    original_autofill = maybe_disable_device_autofill(adb_exe, device_id)

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

    if restore_autofill:
        maybe_restore_device_autofill(adb_exe, device_id, original_autofill)


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
    p.add_argument(
        "--adb",
        type=Path,
        default=None,
        help="Full path to adb.exe (recommended for Jenkins if PATH lacks platform-tools).",
    )
    p.add_argument(
        "--restore-autofill",
        action="store_true",
        help="Restore each device's original autofill service after all flows on that device complete.",
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

    adb_cli = str(args.adb.resolve()) if args.adb else None
    restore_autofill = args.restore_autofill or _truthy_env("AUTOFILL_RESTORE_AFTER_TEST")
    devices = args.devices if args.devices else list_adb_devices(cli_adb=adb_cli)
    if not devices:
        logger.error("No Android devices in 'adb devices'")
        return 1

    adb_exe, _adb_probe = select_working_adb(adb_cli)
    if not adb_exe:
        logger.error("Unable to resolve adb executable for device setup")
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
                adb_exe=adb_exe,
                restore_autofill=restore_autofill,
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
