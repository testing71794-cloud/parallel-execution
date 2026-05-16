#!/usr/bin/env python3
"""
Runtime Maestro CLI capability detection (backward compatible across versions).

Maestro 1.27.x rejects --driver-host-port; newer builds accept it as a global flag
before the test subcommand. Detection uses the same argv shape as run_one_flow_on_device.bat.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

_capabilities: MaestroCapabilities | None = None
_capabilities_lock = threading.Lock()
_driver_port_supported_override: bool | None = None


@dataclass(frozen=True)
class MaestroCapabilities:
    cli_version: str
    driver_host_port_supported: bool
    maestro_mode: str  # isolated_driver_ports | legacy_compatible
    startup_strategy: str

    def log_summary(self) -> None:
        print(
            f"[ATP] maestro_capability driver_port_supported="
            f"{str(self.driver_host_port_supported).lower()}",
            flush=True,
        )
        print(f"[ATP] maestro_cli_version={self.cli_version}", flush=True)
        print(f"[ATP] maestro_mode={self.maestro_mode}", flush=True)
        print(f"[ATP] startup_strategy={self.startup_strategy}", flush=True)


def _java_prefix() -> list[str]:
    from .maestro_runner import build_maestro_java_cmd_prefix

    return build_maestro_java_cmd_prefix()


def _probe_cli_version(prefix: list[str]) -> str:
    for args in (["--version"], ["-v"], ["--help"]):
        try:
            proc = subprocess.run(
                prefix + args,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            text = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if not text:
                continue
            if args != ["--help"]:
                return text.splitlines()[0].strip()[:120]
            m = re.search(r"(\d+\.\d+\.\d+)", text)
            if m:
                return m.group(1)
        except (OSError, subprocess.TimeoutExpired):
            continue
    return "unknown"


def _argv_rejects_driver_port(combined: str) -> bool:
    low = combined.lower()
    if "unknown option" not in low:
        return False
    return "driver-host-port" in low or "driver-port" in low


def _probe_driver_host_port_supported(prefix: list[str]) -> bool:
    """
    Probe using production argv order from run_one_flow_on_device.bat:
      AppKt --driver-host-port <port> --device <id> test ...
    """
    probes = [
        prefix + ["--driver-host-port", "7099", "--device", "127.0.0.1", "test", "--help"],
        prefix + ["--driver-port", "7099", "--device", "127.0.0.1", "test", "--help"],
    ]
    for argv in probes:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            if _argv_rejects_driver_port(combined):
                continue
            if proc.returncode == 0 or "Usage:" in combined:
                flag = "--driver-host-port" if "--driver-host-port" in " ".join(argv) else "--driver-port"
                return flag == "--driver-host-port"
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def invalidate_driver_port_support(*, reason: str) -> None:
    """Runtime fallback when a live run proves the flag is unsupported."""
    global _driver_port_supported_override, _capabilities
    with _capabilities_lock:
        _driver_port_supported_override = False
        if _capabilities is not None:
            _capabilities = MaestroCapabilities(
                cli_version=_capabilities.cli_version,
                driver_host_port_supported=False,
                maestro_mode="legacy_compatible",
                startup_strategy=_legacy_startup_strategy(),
            )
    print(
        f"[ATP] maestro_capability driver_port_supported=false reason=runtime_{reason}",
        flush=True,
    )
    print("[ATP] maestro_mode=legacy_compatible (runtime fallback)", flush=True)
    print(f"[ATP] startup_strategy={_legacy_startup_strategy()}", flush=True)


def driver_host_port_supported() -> bool:
    with _capabilities_lock:
        if _driver_port_supported_override is False:
            return False
        if _capabilities is not None:
            return _capabilities.driver_host_port_supported
    return False


def _legacy_startup_strategy() -> str:
    mutex = legacy_runtime_mutex_default()
    return (
        "serialized_startup_gate+adb_hygiene+host_maestro_cleanup+legacy_stagger"
        + ("+host_runtime_mutex" if mutex else "")
    )


def _isolated_startup_strategy() -> str:
    return "per_device_driver_ports+startup_gate+adb_hygiene+parallel_runtime"


def legacy_runtime_mutex_default() -> bool:
    raw = (os.environ.get("ATP_MAESTRO_LEGACY_RUNTIME_MUTEX") or "auto").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True  # auto: serialize Maestro runs on host when ports unavailable


def legacy_runtime_mutex_active(device_count: int) -> bool:
    if device_count <= 1:
        return False
    if driver_host_port_supported():
        return False
    return legacy_runtime_mutex_default()


def detect_maestro_capabilities(*, device_count: int = 1) -> MaestroCapabilities:
    """Detect once per orchestrator run; cached thereafter."""
    global _capabilities, _driver_port_supported_override
    with _capabilities_lock:
        if _capabilities is not None:
            return _capabilities

        raw_force = (os.environ.get("ATP_MAESTRO_DRIVER_PORTS") or "auto").strip().lower()
        prefix = _java_prefix()
        version = _probe_cli_version(prefix)

        if raw_force in ("0", "false", "no", "off"):
            supported = False
        elif raw_force in ("1", "true", "yes", "on"):
            supported = _probe_driver_host_port_supported(prefix)
        elif device_count <= 1:
            supported = False
        else:
            supported = _probe_driver_host_port_supported(prefix)

        if _driver_port_supported_override is False:
            supported = False

        mode = "isolated_driver_ports" if supported else "legacy_compatible"
        strategy = _isolated_startup_strategy() if supported else _legacy_startup_strategy()

        _capabilities = MaestroCapabilities(
            cli_version=version,
            driver_host_port_supported=supported,
            maestro_mode=mode,
            startup_strategy=strategy,
        )
        _capabilities.log_summary()
        return _capabilities


def maestro_driver_ports_active(device_count: int = 1) -> bool:
    detect_maestro_capabilities(device_count=device_count)
    return driver_host_port_supported()
