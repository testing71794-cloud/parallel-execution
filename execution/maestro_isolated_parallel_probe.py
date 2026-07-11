#!/usr/bin/env python3
"""
Experimental validation: can two Maestro JVM sessions run concurrently on one host
without --driver-host-port, using per-process user.home isolation (ATP model)?

Result is cached per process (keyed by app_home + device pair).
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_probe_cache: dict[str, IsolatedParallelProbeResult] = {}
_probe_lock = threading.Lock()

_COLLISION_PATTERNS = (
    re.compile(r"localhost:7001.*(refused|closed|timeout)", re.I),
    re.compile(r"allocateForwarder", re.I),
    re.compile(r"TcpForwarder\.waitFor", re.I),
    re.compile(r"Command failed \(tcp:7001\)", re.I),
    re.compile(r"Address already in use", re.I),
    re.compile(r"Failed to allocate port", re.I),
    re.compile(r"No available ports found", re.I),
)

_SUCCESS_PATTERNS = (
    re.compile(r"^\s*>\s", re.M),  # hierarchy tree lines
    re.compile(r"Starting Maestro", re.I),
    re.compile(r"Run .*\.yaml", re.I),
    re.compile(r"COMPLETED", re.I),
)


@dataclass(frozen=True)
class IsolatedParallelProbeResult:
    supported: bool
    detail: str
    device_a: str
    device_b: str
    duration_sec: float


def _adb_exe() -> str | None:
    for root_env in ("ADB_HOME", "ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(root_env, "").strip().strip('"')
        if not root:
            continue
        if "platform-tools" in root.replace("\\", "/").lower():
            exe = Path(root) / ("adb.exe" if os.name == "nt" else "adb")
        else:
            exe = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        if exe.is_file():
            return str(exe)
    if os.name == "nt":
        user = os.environ.get("USERPROFILE", "").strip()
        if user:
            fallback = (
                Path(user)
                / "AppData"
                / "Local"
                / "Android"
                / "Sdk"
                / "platform-tools"
                / "adb.exe"
            )
            if fallback.is_file():
                return str(fallback)
    import shutil

    w = shutil.which("adb")
    return w


def _list_devices() -> list[str]:
    exe = _adb_exe()
    if not exe:
        return []
    try:
        proc = subprocess.run(
            [exe, "devices"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    out: list[str] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            out.append(parts[0])
    return out


def _experimental_probe_enabled() -> bool:
    raw = (os.environ.get("ATP_MAESTRO_EXPERIMENTAL_ISOLATED_PROBE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _collision_in(text: str) -> bool:
    return any(p.search(text) for p in _COLLISION_PATTERNS)


def _success_in(text: str) -> bool:
    return any(p.search(text) for p in _SUCCESS_PATTERNS)


def _classify_probe_failure(
    *,
    code_a: int,
    code_b: int,
    combined: str,
    errors: dict[str, str],
) -> str:
    if errors or "python_exception:" in combined:
        return f"python_exception:{next(iter(errors.values()), 'worker_failed')}"
    low = combined.lower()
    if "not recognized" in low and "maestro" in low:
        return "maestro_cli_missing"
    if "adb" in low and ("not found" in low or "no devices" in low or "device offline" in low):
        return "adb_failure"
    if _collision_in(combined):
        return "runtime_collision:port_7001_or_forwarder"
    if "unknown options" in low or "unrecognized option" in low:
        return "unsupported_cli"
    if code_a == 124 or code_b == 124:
        return f"probe_timeout exit=({code_a},{code_b})"
    return f"concurrent_failed exit=({code_a},{code_b})"


def _run_isolated_hierarchy(
    *,
    app_home: Path,
    device_id: str,
    work_root: Path,
    timeout_sec: float,
) -> tuple[int, str]:
    import re as re_module

    from .maestro_install_resolver import build_java_prefix_for_app_home

    prefix = build_java_prefix_for_app_home(app_home)
    slug = re_module.sub(r"[^\w\-.]+", "_", device_id)
    runtime_home = (work_root / f"probe_{slug}").resolve()
    runtime_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["ANDROID_SERIAL"] = device_id
    env.pop("ANDROID_DEBUG_SERIAL", None)
    env.pop("MAESTRO_OPTS", None)
    env["ATP_JAVA_USER_HOME"] = str(runtime_home)
    env["TMP"] = str(runtime_home / "tmp")
    env["TEMP"] = str(runtime_home / "tmp")
    Path(env["TMP"]).mkdir(parents=True, exist_ok=True)

    # Global options must precede subcommand (picocli); --device on hierarchy alone prompts interactively.
    cmd = prefix + ["--device", device_id, "hierarchy"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, combined
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "") + (e.stderr or "")
        return 124, partial + "\n[probe] timeout"


def run_isolated_parallel_probe(
    app_home: Path,
    *,
    devices: list[str] | None = None,
    timeout_sec: float | None = None,
    repo: Path | None = None,
) -> IsolatedParallelProbeResult:
    """
    Launch two Maestro hierarchy commands concurrently with isolated user.home dirs.
    supported=True only if both complete without known port-collision signatures.
    """
    cache_key = str(app_home.resolve()).lower()
    with _probe_lock:
        if cache_key in _probe_cache:
            return _probe_cache[cache_key]

    if not _experimental_probe_enabled():
        result = IsolatedParallelProbeResult(
            supported=False,
            detail="probe_disabled:ATP_MAESTRO_EXPERIMENTAL_ISOLATED_PROBE=0",
            device_a="",
            device_b="",
            duration_sec=0.0,
        )
        _probe_cache[cache_key] = result
        return result

    devs = devices if devices else _list_devices()
    if len(devs) < 2:
        result = IsolatedParallelProbeResult(
            supported=False,
            detail=f"insufficient_devices:{len(devs)}",
            device_a=devs[0] if devs else "",
            device_b="",
            duration_sec=0.0,
        )
        _probe_cache[cache_key] = result
        return result

    device_a, device_b = devs[0], devs[1]
    tmo = timeout_sec
    if tmo is None:
        try:
            tmo = float((os.environ.get("ATP_MAESTRO_ISOLATED_PROBE_TIMEOUT_SEC") or "60").strip())
        except ValueError:
            tmo = 60.0

    from .maestro_probe_cache import load_isolated_probe, save_isolated_probe

    cached = load_isolated_probe(repo=repo, app_home=app_home, devices=devs[:2])
    if cached is not None:
        supported, detail = cached
        result = IsolatedParallelProbeResult(
            supported=supported,
            detail=detail,
            device_a=device_a,
            device_b=device_b,
            duration_sec=0.0,
        )
        with _probe_lock:
            _probe_cache[cache_key] = result
        return result

    print(
        f"[ATP] isolated_runtime_probe begin devices={device_a},{device_b} "
        f"app_home={app_home} timeout_sec={tmo:.0f} (concurrent hierarchy; may take ~30-60s)",
        flush=True,
    )

    work_root = Path(tempfile.mkdtemp(prefix="atp_maestro_isolated_probe_"))
    results: dict[str, tuple[int, str]] = {}
    t0 = time.time()

    errors: dict[str, str] = {}

    def worker(dev: str) -> None:
        try:
            results[dev] = _run_isolated_hierarchy(
                app_home=app_home,
                device_id=dev,
                work_root=work_root,
                timeout_sec=tmo,
            )
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            errors[dev] = f"{exc}"
            results[dev] = (1, f"python_exception:{exc}\n{tb}")
            print(
                f"[ATP] isolated_runtime_probe worker_error device={dev} error={exc}",
                flush=True,
            )

    th_a = threading.Thread(target=worker, args=(device_a,), name=f"probe_{device_a}")
    th_b = threading.Thread(target=worker, args=(device_b,), name=f"probe_{device_b}")
    th_a.start()
    th_b.start()
    th_a.join()
    th_b.join()
    elapsed = time.time() - t0

    try:
        shutil_rmtree = __import__("shutil").rmtree
        shutil_rmtree(work_root, ignore_errors=True)
    except OSError:
        pass

    code_a, out_a = results.get(device_a, (1, ""))
    code_b, out_b = results.get(device_b, (1, ""))
    combined = out_a + "\n" + out_b

    fail_detail = _classify_probe_failure(
        code_a=code_a, code_b=code_b, combined=combined, errors=errors
    )
    if code_a == 0 and code_b == 0:
        result = IsolatedParallelProbeResult(
            supported=True,
            detail="concurrent_hierarchy_ok",
            device_a=device_a,
            device_b=device_b,
            duration_sec=elapsed,
        )
    elif _success_in(combined) and not _collision_in(combined):
        result = IsolatedParallelProbeResult(
            supported=True,
            detail=f"concurrent_partial_ok exit=({code_a},{code_b})",
            device_a=device_a,
            device_b=device_b,
            duration_sec=elapsed,
        )
    else:
        result = IsolatedParallelProbeResult(
            supported=False,
            detail=fail_detail,
            device_a=device_a,
            device_b=device_b,
            duration_sec=elapsed,
        )

    with _probe_lock:
        _probe_cache[cache_key] = result
    save_isolated_probe(
        repo=repo,
        app_home=app_home,
        devices=[device_a, device_b],
        supported=result.supported,
        detail=result.detail,
    )
    return result


def log_probe_result(result: IsolatedParallelProbeResult) -> None:
    print(
        f"[ATP] isolated_runtime_probe supported={str(result.supported).lower()} "
        f"detail={result.detail} devices={result.device_a},{result.device_b} "
        f"duration_sec={result.duration_sec:.1f}",
        flush=True,
    )
