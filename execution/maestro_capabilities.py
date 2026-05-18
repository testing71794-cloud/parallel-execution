#!/usr/bin/env python3
"""
Maestro parallel capability detection for ATP orchestration.

Detection order (behavior-based, not version strings):
1. CLI accepts global --driver-host-port (or --host-port) before subcommand
2. Else: experimental concurrent isolated JVM sessions (per-device user.home)
3. Else: legacy_compatible serialized mode
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from .maestro_install_resolver import (
    MaestroInstallCandidate,
    probe_install,
    resolve_maestro_for_parallel,
)
from .maestro_runtime_diagnostics import emit_parallel_readiness_report

_capabilities: MaestroCapabilities | None = None
_capabilities_lock = threading.Lock()
_driver_port_supported_override: bool | None = None
_isolated_runtime_override: bool | None = None
_selected_install: MaestroInstallCandidate | None = None
_runtime_config_logged = False
_legacy_fallback_logged = False


@dataclass(frozen=True)
class MaestroCapabilities:
    cli_version: str
    driver_host_port_supported: bool
    isolated_runtime_supported: bool
    parallel_capability: str  # driver_port | isolated_runtime | none
    maestro_mode: str  # native_parallel | legacy_compatible
    startup_strategy: str
    maestro_home: str
    maestro_app_home: str
    native_parallel_enabled: bool
    native_parallel_reason: str
    capability_detection_source: str

    def log_summary(self, *, device_count: int = 1) -> None:
        print(
            f"[ATP] maestro_capability driver_port_supported="
            f"{str(self.driver_host_port_supported).lower()}",
            flush=True,
        )
        print(
            f"[ATP] maestro_capability isolated_runtime_supported="
            f"{str(self.isolated_runtime_supported).lower()}",
            flush=True,
        )
        print(f"[ATP] maestro_capability parallel_mode={self.parallel_capability}", flush=True)
        print(f"[ATP] maestro_capability detection_source={self.capability_detection_source}", flush=True)
        print(f"[ATP] maestro_cli_version={self.cli_version}", flush=True)
        print(f"[ATP] maestro_mode={self.maestro_mode}", flush=True)
        print(f"[ATP] startup_strategy={self.startup_strategy}", flush=True)
        print(f"[ATP] maestro_home={self.maestro_home}", flush=True)
        print(f"[ATP] maestro_app_home={self.maestro_app_home}", flush=True)
        np = device_count > 1 and self.native_parallel_enabled
        print(f"[ATP] native_parallel={1 if np else 0}", flush=True)
        print(f"[ATP] native_parallel_reason={self.native_parallel_reason}", flush=True)


def require_native_parallel() -> bool:
    return os.environ.get("ATP_REQUIRE_NATIVE_PARALLEL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def legacy_serialized_allowed() -> bool:
    if require_native_parallel():
        return False
    raw = (os.environ.get("ATP_ALLOW_LEGACY_SERIALIZED") or "auto").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def invalidate_driver_port_support(*, reason: str) -> None:
    global _driver_port_supported_override, _capabilities
    with _capabilities_lock:
        _driver_port_supported_override = False
        _rebuild_capabilities_after_invalidate(reason=reason)


def invalidate_isolated_runtime_support(*, reason: str) -> None:
    global _isolated_runtime_override, _capabilities, _runtime_config_logged
    with _capabilities_lock:
        _isolated_runtime_override = False
        os.environ.pop("ATP_NATIVE_PARALLEL_ACTIVE", None)
        _runtime_config_logged = False
        _rebuild_capabilities_after_invalidate(reason=reason)
    print(f"[ATP] fallback_reason=runtime_collision:{reason}", flush=True)
    apply_legacy_parallel_env_defaults()


def _rebuild_capabilities_after_invalidate(*, reason: str) -> None:
    global _capabilities
    if _capabilities is None:
        return
    inst = _selected_install
    if inst is None:
        return
    device_count = int(os.environ.get("ATP_ORCH_DEVICE_COUNT", "2") or "2")
    _capabilities = _capabilities_from_install(inst, device_count=device_count, force_reason=reason)


def driver_host_port_supported() -> bool:
    with _capabilities_lock:
        if _driver_port_supported_override is False:
            return False
        if _capabilities is not None:
            return _capabilities.driver_host_port_supported
    return False


def isolated_runtime_supported() -> bool:
    with _capabilities_lock:
        if _isolated_runtime_override is False:
            return False
        if _capabilities is not None:
            return _capabilities.isolated_runtime_supported
    return False


def native_parallel_active(device_count: int = 1) -> bool:
    if device_count <= 1:
        return False
    caps = detect_maestro_capabilities(device_count=device_count)
    return caps.native_parallel_enabled


def _native_startup_strategy(parallel_capability: str) -> str:
    if parallel_capability == "driver_port":
        return (
            "native_parallel:per_device_driver_ports+adb_hygiene+"
            "no_startup_gate+no_runtime_mutex+worker_pool"
        )
    return (
        "native_parallel:isolated_user_home+adb_hygiene+"
        "no_startup_gate+no_runtime_mutex+worker_pool"
    )


def _legacy_startup_strategy() -> str:
    return "legacy_compatible:host_runtime_mutex+startup_gate+adb_hygiene"


def legacy_runtime_mutex_active(device_count: int) -> bool:
    if device_count <= 1:
        return False
    if native_parallel_active(device_count):
        return False
    if not legacy_serialized_allowed():
        return False
    raw = (os.environ.get("ATP_MAESTRO_LEGACY_RUNTIME_MUTEX") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def apply_legacy_parallel_env_defaults() -> None:
    os.environ.setdefault("ATP_MAESTRO_STARTUP_GATE", "1")
    os.environ.setdefault("ATP_MAESTRO_LEGACY_RUNTIME_MUTEX", "1")
    os.environ.setdefault("ATP_MAESTRO_DRIVER_PORTS", "0")
    if os.name == "nt":
        os.environ.setdefault("ATP_PARALLEL_DEVICE_STAGGER_SEC", "2")
    os.environ.setdefault("MAESTRO_PARALLEL_STARTUP_DELAY_SEC", "8")


def apply_native_parallel_env_defaults(
    *,
    device_count: int,
    caps: MaestroCapabilities | None = None,
) -> None:
    if device_count <= 1:
        return
    if caps is None:
        caps = detect_maestro_capabilities(device_count=device_count)
    if not caps.native_parallel_enabled:
        return
    # Force native runtime policy (override stale Jenkins env).
    os.environ["ATP_MAESTRO_STARTUP_GATE"] = "0"
    os.environ.setdefault("ATP_PARALLEL_DEVICE_STAGGER_SEC", "2")
    os.environ["ATP_MAESTRO_LEGACY_RUNTIME_MUTEX"] = "0"
    os.environ["ATP_MAESTRO_HANDSHAKE_GATE"] = "0"
    os.environ["MAESTRO_PARALLEL_STARTUP_DELAY_SEC"] = "0"
    os.environ["ATP_NATIVE_PARALLEL_ACTIVE"] = "1"
    if caps.driver_host_port_supported:
        os.environ["ATP_MAESTRO_DRIVER_PORTS"] = "1"
    else:
        os.environ["ATP_MAESTRO_DRIVER_PORTS"] = "0"


def log_native_parallel_runtime_config(caps: MaestroCapabilities) -> None:
    global _runtime_config_logged
    if _runtime_config_logged:
        return
    _runtime_config_logged = True
    print("[ATP] native_parallel_runtime_config begin", flush=True)
    print(f"[ATP] maestro_mode={caps.maestro_mode}", flush=True)
    print(f"[ATP] native_parallel=1", flush=True)
    print(f"[ATP] native_parallel_enable_reason={caps.native_parallel_reason}", flush=True)
    print(f"[ATP] capability_detection_source={caps.capability_detection_source}", flush=True)
    print(
        f"[ATP] maestro_capability driver_port_supported="
        f"{str(caps.driver_host_port_supported).lower()}",
        flush=True,
    )
    print(
        f"[ATP] maestro_capability isolated_runtime_supported="
        f"{str(caps.isolated_runtime_supported).lower()}",
        flush=True,
    )
    print("[ATP] maestro_startup_gate=0", flush=True)
    stagger = (os.environ.get("ATP_PARALLEL_DEVICE_STAGGER_SEC") or "2").strip()
    print(f"[ATP] parallel_device_stagger_sec={stagger}", flush=True)
    print("[ATP] legacy_runtime_mutex=0", flush=True)
    print("[ATP] native_parallel_runtime_config end", flush=True)


def is_native_parallel_env_active() -> bool:
    return os.environ.get("ATP_NATIVE_PARALLEL_ACTIVE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _forced_isolated_parallel() -> bool:
    return os.environ.get("ATP_MAESTRO_ISOLATED_PARALLEL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _run_isolated_probe(
    inst: MaestroInstallCandidate,
    *,
    device_count: int,
    devices: list[str] | None = None,
    repo: Path | None = None,
) -> MaestroInstallCandidate:
    if device_count <= 1:
        return inst
    if _forced_isolated_parallel():
        return MaestroInstallCandidate(
            label=inst.label,
            bin_dir=inst.bin_dir,
            app_home=inst.app_home,
            launcher=inst.launcher,
            cli_version=inst.cli_version,
            driver_host_port_supported=inst.driver_host_port_supported,
            probe_detail=inst.probe_detail,
            lib_mtime=inst.lib_mtime,
            isolated_runtime_supported=True,
            isolated_probe_detail="forced:ATP_MAESTRO_ISOLATED_PARALLEL=1",
            internal_driver_port_api=inst.internal_driver_port_api,
        )
    from .maestro_isolated_parallel_probe import log_probe_result, run_isolated_parallel_probe

    result = run_isolated_parallel_probe(inst.app_home, devices=devices, repo=repo)
    log_probe_result(result)
    return MaestroInstallCandidate(
        label=inst.label,
        bin_dir=inst.bin_dir,
        app_home=inst.app_home,
        launcher=inst.launcher,
        cli_version=inst.cli_version,
        driver_host_port_supported=inst.driver_host_port_supported,
        probe_detail=inst.probe_detail,
        lib_mtime=inst.lib_mtime,
        isolated_runtime_supported=result.supported,
        isolated_probe_detail=result.detail,
        internal_driver_port_api=inst.internal_driver_port_api,
    )


def _capabilities_from_install(
    inst: MaestroInstallCandidate,
    *,
    device_count: int,
    force_reason: str | None = None,
) -> MaestroCapabilities:
    driver_port = inst.driver_host_port_supported
    isolated = inst.isolated_runtime_supported
    if _driver_port_supported_override is False:
        driver_port = False
    if _isolated_runtime_override is False:
        isolated = False
    if device_count <= 1:
        driver_port = False
        isolated = False

    if driver_port:
        parallel_capability = "driver_port"
        detection_source = f"cli_argv:{inst.probe_detail}"
        native = True
        mode = "native_parallel"
        strategy = _native_startup_strategy(parallel_capability)
        reason = force_reason or f"install={inst.label} {inst.probe_detail}"
    elif isolated:
        parallel_capability = "isolated_runtime"
        detection_source = f"experimental_probe:{inst.isolated_probe_detail}"
        native = True
        mode = "native_parallel"
        strategy = _native_startup_strategy(parallel_capability)
        reason = force_reason or (
            f"install={inst.label} concurrent_isolated_sessions_ok "
            f"(probe={inst.isolated_probe_detail}); CLI has no global --driver-host-port"
        )
    else:
        parallel_capability = "none"
        detection_source = f"cli_argv:{inst.probe_detail}"
        native = False
        mode = "legacy_compatible"
        strategy = _legacy_startup_strategy()
        if inst.internal_driver_port_api:
            extra = " (internal driverHostPort API present but CLI flag not exposed)"
        else:
            extra = ""
        reason = force_reason or (
            f"install={inst.label} no_driver_port_cli and isolated_probe_failed "
            f"({inst.isolated_probe_detail}){extra}"
        )

    return MaestroCapabilities(
        cli_version=inst.cli_version,
        driver_host_port_supported=driver_port,
        isolated_runtime_supported=isolated,
        parallel_capability=parallel_capability,
        maestro_mode=mode,
        startup_strategy=strategy,
        maestro_home=str(inst.bin_dir),
        maestro_app_home=str(inst.app_home),
        native_parallel_enabled=native and device_count > 1,
        native_parallel_reason=reason,
        capability_detection_source=detection_source,
    )


def assert_native_parallel_ready(
    *,
    device_count: int,
    devices: list[str] | None = None,
    repo: Path | None = None,
) -> None:
    global _legacy_fallback_logged
    if device_count <= 1:
        return
    print(
        "[ATP] maestro_capability_detection begin "
        "(install probe + optional isolated runtime validation; progress lines follow)",
        flush=True,
    )
    caps = detect_maestro_capabilities(device_count=device_count, devices=devices, repo=repo)
    if caps.native_parallel_enabled:
        apply_native_parallel_env_defaults(device_count=device_count, caps=caps)
        log_native_parallel_runtime_config(caps)
        return
    if legacy_serialized_allowed():
        apply_legacy_parallel_env_defaults()
        if not _legacy_fallback_logged:
            _legacy_fallback_logged = True
            print(
                "[ATP] native_parallel=0 maestro_mode=legacy_compatible "
                f"(CLI {caps.cli_version}; {caps.native_parallel_reason})",
                flush=True,
            )
            print(
                "[ATP] fallback_reason=no_driver_port_cli_and_isolated_probe_failed",
                flush=True,
            )
        return
    print(
        "\nERROR: True parallel requires --driver-host-port CLI or passing isolated runtime probe.\n"
        f"  Selected: {caps.maestro_home}\n"
        f"  Reason: {caps.native_parallel_reason}\n",
        flush=True,
    )
    sys.exit(2)


def _orch_devices(devices: list[str] | None) -> list[str] | None:
    if devices:
        return devices
    raw = (os.environ.get("ATP_ORCH_DEVICES") or "").strip()
    if not raw:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


def detect_maestro_capabilities(
    *,
    device_count: int = 1,
    maestro_cmd: str | None = None,
    resolve_installs: bool = True,
    devices: list[str] | None = None,
    repo: Path | None = None,
) -> MaestroCapabilities:
    global _capabilities, _selected_install
    devices = _orch_devices(devices)
    with _capabilities_lock:
        if _capabilities is not None:
            return _capabilities

        if resolve_installs:
            _selected_install = resolve_maestro_for_parallel(
                maestro_cmd=maestro_cmd,
                device_count=max(device_count, 1),
            )
        elif (mh := os.environ.get("MAESTRO_HOME", "").strip()):
            _selected_install = probe_install(Path(mh), label="MAESTRO_HOME")

        if _selected_install is None:
            mh = os.environ.get("MAESTRO_HOME", "").strip().strip('"')
            if not mh:
                raise RuntimeError("MAESTRO_HOME not set and no Maestro install discovered")
            _selected_install = probe_install(Path(mh), label="fallback")

        if _selected_install is None:
            raise RuntimeError("No valid Maestro installation found on this host")

        raw_force = (os.environ.get("ATP_MAESTRO_DRIVER_PORTS") or "auto").strip().lower()
        if raw_force in ("0", "false", "no", "off"):
            _selected_install = MaestroInstallCandidate(
                label=_selected_install.label,
                bin_dir=_selected_install.bin_dir,
                app_home=_selected_install.app_home,
                launcher=_selected_install.launcher,
                cli_version=_selected_install.cli_version,
                driver_host_port_supported=False,
                probe_detail="ATP_MAESTRO_DRIVER_PORTS=0",
                lib_mtime=_selected_install.lib_mtime,
                isolated_runtime_supported=_selected_install.isolated_runtime_supported,
                isolated_probe_detail=_selected_install.isolated_probe_detail,
                internal_driver_port_api=_selected_install.internal_driver_port_api,
            )

        if not _selected_install.driver_host_port_supported:
            _selected_install = _run_isolated_probe(
                _selected_install,
                device_count=device_count,
                devices=devices,
                repo=repo,
            )

        emit_parallel_readiness_report(
            maestro_cmd=maestro_cmd,
            device_count=device_count,
            selected=_selected_install,
            known_installs=[_selected_install] if _selected_install else None,
        )
        print("[ATP] maestro_capability_detection end", flush=True)

        _capabilities = _capabilities_from_install(_selected_install, device_count=device_count)
        _capabilities.log_summary(device_count=device_count)
        return _capabilities


def maestro_driver_ports_active(device_count: int = 1) -> bool:
    detect_maestro_capabilities(device_count=device_count)
    return driver_host_port_supported()
