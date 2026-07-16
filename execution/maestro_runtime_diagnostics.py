#!/usr/bin/env python3
"""
Enterprise Maestro runtime diagnostics: install inventory, PATH conflicts, capability probes.

Does not modify test flows. Safe to call at orchestrator startup.
"""
from __future__ import annotations

import os
from pathlib import Path

from .maestro_install_resolver import (
    MaestroInstallCandidate,
    build_java_prefix_for_app_home,
    discover_maestro_installs,
    probe_install,
)


def _env_snapshot() -> dict[str, str]:
    keys = (
        "MAESTRO_HOME",
        "ATP_MAESTRO_PARALLEL_HOME",
        "ATP_MAESTRO_HOME_CANDIDATES",
        "ATP_MAESTRO_SELECTED_INSTALL",
        "JAVA_HOME",
        "MAESTRO_JAVA_HOME",
        "PATH",
        "ATP_MAESTRO_DRIVER_PORTS",
        "ATP_ALLOW_LEGACY_SERIALIZED",
        "ATP_REQUIRE_NATIVE_PARALLEL",
        "ATP_MAESTRO_PREFER_LATEST",
        "ATP_MAESTRO_INSTALL_SCAN",
    )
    return {k: (os.environ.get(k) or "").strip() for k in keys}


def _path_maestro_conflicts() -> list[str]:
    conflicts: list[str] = []
    path = os.environ.get("PATH", "")
    seen: dict[str, str] = {}
    for part in path.split(os.pathsep):
        part = part.strip().strip('"')
        if not part:
            continue
        for name in ("maestro.bat", "maestro.cmd", "maestro"):
            p = Path(part) / name
            if p.is_file():
                key = str(p.resolve()).lower()
                if key in seen:
                    conflicts.append(f"duplicate_on_path: {p} (also {seen[key]})")
                else:
                    seen[key] = str(p)
    return conflicts


def _jar_inventory(app_home: Path, *, limit: int = 5) -> list[str]:
    lib = app_home / "lib"
    if not lib.is_dir():
        return []
    jars = sorted(lib.glob("*.jar"), key=lambda p: p.stat().st_mtime, reverse=True)
    lines: list[str] = []
    for j in jars[:limit]:
        try:
            st = j.stat()
            lines.append(f"{j.name} mtime={st.st_mtime:.0f} size={st.st_size}")
        except OSError:
            lines.append(j.name)
    return lines


def _core_version_hint(app_home: Path) -> str:
    """Best-effort Core/UI version from maestro-cli jar manifest or properties (not CLI --version)."""
    lib = app_home / "lib"
    if not lib.is_dir():
        return "unknown"
    for pattern in ("maestro-cli*.jar", "cli*.jar", "*.jar"):
        for jar in sorted(lib.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)[:3]:
            try:
                import zipfile

                with zipfile.ZipFile(jar, "r") as zf:
                    for name in zf.namelist():
                        if name.endswith("version.properties") or name.endswith("META-INF/MANIFEST.MF"):
                            data = zf.read(name).decode("utf-8", errors="replace")[:800]
                            for line in data.splitlines():
                                low = line.lower()
                                if "version" in low or "maestro" in low:
                                    return line.strip()[:120]
            except (OSError, zipfile.BadZipFile):
                continue
    return "see_cli_version"


def build_runtime_mapping(
    *,
    maestro_cmd: str | None = None,
    selected: MaestroInstallCandidate | None = None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if selected is None:
        installs = discover_maestro_installs(maestro_cmd=maestro_cmd)
        if installs:
            selected = installs[0]
    if selected:
        from .maestro_runner import resolve_maestro_java_exe

        prefix = build_java_prefix_for_app_home(selected.app_home)
        mapping["maestro_launcher"] = str(selected.launcher)
        mapping["maestro_bin_dir"] = str(selected.bin_dir)
        mapping["maestro_app_home"] = str(selected.app_home)
        mapping["java_executable"] = str(resolve_maestro_java_exe())
        mapping["java_argv_prefix"] = " ".join(prefix[:4]) + " ..."
        mapping["cli_version"] = selected.cli_version
        mapping["driver_host_port_supported"] = str(selected.driver_host_port_supported).lower()
        mapping["isolated_runtime_supported"] = str(
            getattr(selected, "isolated_runtime_supported", False)
        ).lower()
        mapping["capability_probe"] = selected.probe_detail
        mapping["isolated_probe"] = getattr(selected, "isolated_probe_detail", "n/a")
        mapping["internal_driver_port_api"] = str(
            getattr(selected, "internal_driver_port_api", False)
        ).lower()
        mapping["lib_jars_newest"] = "; ".join(_jar_inventory(selected.app_home))
        mapping["core_version_hint"] = _core_version_hint(selected.app_home)
    return mapping


def emit_parallel_readiness_report(
    *,
    maestro_cmd: str | None = None,
    device_count: int = 1,
    selected: MaestroInstallCandidate | None = None,
    known_installs: list[MaestroInstallCandidate] | None = None,
) -> None:
    """Print full runtime report to stdout (ATP log)."""
    env = _env_snapshot()
    print("[ATP] maestro_runtime_report begin", flush=True)
    print("[ATP] parallel_readiness inherited_env:", flush=True)
    for k, v in env.items():
        if not v and k != "PATH":
            continue
        if k == "PATH":
            print(f"  {k}=<len={len(v)}>", flush=True)
        else:
            print(f"  {k}={v}", flush=True)

    conflicts = _path_maestro_conflicts()
    if conflicts:
        print("[ATP] path_conflict maestro_on_path=yes", flush=True)
        for c in conflicts:
            print(f"  {c}", flush=True)
    else:
        print("[ATP] path_conflict maestro_on_path=no (MAESTRO_HOME resolution only)", flush=True)

    installs = known_installs if known_installs is not None else discover_maestro_installs(maestro_cmd=maestro_cmd)
    print(f"[ATP] maestro_install_inventory count={len(installs)}", flush=True)
    for inst in installs:
        print(inst.log_line(), flush=True)
        jars = _jar_inventory(inst.app_home, limit=2)
        if jars:
            print(f"    newest_jars={'; '.join(jars)}", flush=True)

    if selected is None and installs:
        selected = installs[0]

    mapping = build_runtime_mapping(maestro_cmd=maestro_cmd, selected=selected)
    print("[ATP] maestro_runtime_mapping selected:", flush=True)
    for k, v in mapping.items():
        print(f"  {k}={v}", flush=True)

    if device_count > 1:
        iso = getattr(selected, "isolated_runtime_supported", False)
        if selected and (selected.driver_host_port_supported or iso):
            mode = "driver_port" if selected.driver_host_port_supported else "isolated_runtime"
            verdict = f"READY native_parallel=1 mode={mode}"
        else:
            verdict = (
                "BLOCKED native_parallel=0: no driver_port CLI and isolated probe failed "
                f"(best_cli={selected.cli_version if selected else '?'})"
            )
        print(f"[ATP] parallel_readiness_verdict {verdict}", flush=True)
        if selected and not selected.driver_host_port_supported and not iso:
            print(
                "[ATP] parallel_readiness_root_cause "
                "Maestro CLI rejects --driver-host-port at runtime (not an orchestrator bug). "
                "Jenkins MAESTRO_HOME may point at an older tree; set ATP_MAESTRO_PARALLEL_HOME or "
                "upgrade to a build containing PR #2821.",
                flush=True,
            )
    print("[ATP] maestro_runtime_report end", flush=True)


def probe_driver_port_functional(app_home: Path) -> tuple[bool, str]:
    """Standalone functional probe for scripts."""
    cand = probe_install(app_home / "bin" if (app_home / "bin").is_dir() else app_home, label="probe")
    if cand is None:
        return False, "invalid_install"
    return cand.driver_host_port_supported, cand.probe_detail
