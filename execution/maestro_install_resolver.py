#!/usr/bin/env python3
"""
Discover Maestro installations on the host and select one that supports --driver-host-port.

Jenkins agents often pin MAESTRO_HOME to an older tree (e.g. 1.27.x) while a newer CLI
may exist elsewhere on disk. This module probes each candidate and can repoint MAESTRO_HOME
for the orchestrator process when a parallel-capable build is found.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

_last_selection_reason: str = "unknown"


def get_maestro_selection_reason() -> str:
    return _last_selection_reason


def _set_selection_reason(reason: str) -> None:
    global _last_selection_reason
    _last_selection_reason = reason


def _parse_cli_version_tuple(version: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", version or "")]
    return tuple(nums) if nums else (0,)


@dataclass(frozen=True)
class MaestroInstallCandidate:
    label: str
    bin_dir: Path
    app_home: Path
    launcher: Path
    cli_version: str
    driver_host_port_supported: bool
    probe_detail: str
    lib_mtime: float | None
    isolated_runtime_supported: bool = False
    isolated_probe_detail: str = "not_run"
    internal_driver_port_api: bool = False

    def log_line(self) -> str:
        sup = "yes" if self.driver_host_port_supported else "no"
        return (
            f"  [{self.label}] home={self.bin_dir} version={self.cli_version} "
            f"driver_port={sup} probe={self.probe_detail}"
        )


def _java_exe() -> Path:
    from .maestro_runner import resolve_maestro_java_exe

    return resolve_maestro_java_exe()


def build_java_prefix_for_app_home(app_home: Path) -> list[str]:
    lib_glob = str((app_home / "lib" / "*").resolve())
    return [str(_java_exe()), "-classpath", lib_glob, "maestro.cli.AppKt"]


def _argv_rejects_option(combined: str, option_token: str) -> bool:
    low = combined.lower()
    if "unknown option" not in low:
        return False
    return option_token.lower() in low


def _argv_rejects_driver_port(combined: str) -> bool:
    low = combined.lower()
    if "unknown option" not in low:
        return False
    return "driver-host-port" in low or "driver-port" in low or "host-port" in low


def _jar_has_internal_driver_port_api(app_home: Path) -> bool:
    try:
        import zipfile

        for cli_jar in sorted(app_home.glob("lib/maestro-cli*.jar"), reverse=True):
            with zipfile.ZipFile(cli_jar, "r") as zf:
                for cls in (
                    "maestro/cli/command/TestCommand.class",
                    "maestro/cli/session/MaestroSessionManager.class",
                ):
                    if cls in zf.namelist() and b"driverHostPort" in zf.read(cls):
                        return True
    except OSError:
        return False
    return False


def _help_mentions_driver_port(text: str) -> bool:
    low = text.lower()
    return "driver-host-port" in low or "driver-hostport" in low or "driver-port" in low


def _probe_cli_version(prefix: list[str]) -> str:
    for args in (["--version"], ["-v"]):
        try:
            proc = subprocess.run(
                prefix + args,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            text = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if text:
                return text.splitlines()[0].strip()[:120]
        except (OSError, subprocess.TimeoutExpired):
            continue
    return "unknown"


def _lib_mtime(app_home: Path) -> float | None:
    lib_dir = app_home / "lib"
    if not lib_dir.is_dir():
        return None
    try:
        jars = list(lib_dir.glob("*.jar"))
        if not jars:
            return None
        return max(p.stat().st_mtime for p in jars)
    except OSError:
        return None


def _quick_probe_mode() -> bool:
    raw = (os.environ.get("ATP_MAESTRO_QUICK_PROBE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def probe_install(bin_dir: Path, *, label: str) -> MaestroInstallCandidate | None:
    """Probe one Maestro bin directory for launcher + driver-host-port support."""
    t0 = time.time()
    print(f"[ATP] maestro_install_probe begin label={label} path={bin_dir}", flush=True)
    bin_dir = bin_dir.resolve()
    launcher: Path | None = None
    for name in ("maestro.bat", "maestro.cmd"):
        cand = bin_dir / name
        if cand.is_file():
            launcher = cand
            break
    if launcher is None:
        print(f"[ATP] maestro_install_probe skip label={label} reason=no_launcher", flush=True)
        return None

    if bin_dir.name.lower() in ("bin", "scripts"):
        app_home = bin_dir.parent
    else:
        app_home = bin_dir

    lib_dir = app_home / "lib"
    if not lib_dir.is_dir():
        return None

    prefix = build_java_prefix_for_app_home(app_home)
    version = _probe_cli_version(prefix)

    help_global = ""
    help_test_cmd = ""
    help_test = ""
    supported = False
    detail = "not_probed"
    detection_source = "cli_argv"
    internal_api = _jar_has_internal_driver_port_api(app_home)
    probe_timeout = 30 if _quick_probe_mode() else 45
    try:
        if not _quick_probe_mode():
            p1 = subprocess.run(
                prefix + ["--help"],
                capture_output=True,
                text=True,
                timeout=probe_timeout,
                check=False,
            )
            help_global = (p1.stdout or "") + (p1.stderr or "")
            p_test_help = subprocess.run(
                prefix + ["test", "--help"],
                capture_output=True,
                text=True,
                timeout=probe_timeout,
                check=False,
            )
            help_test_cmd = (p_test_help.stdout or "") + (p_test_help.stderr or "")

        argv_variants = [
            (["--driver-host-port", "7099", "--device", "127.0.0.1", "test", "--help"], "driver-host-port_space"),
        ]
        if not _quick_probe_mode():
            argv_variants.extend(
                [
                    (["--driver-host-port=7099", "--device", "127.0.0.1", "test", "--help"], "driver-host-port_equals"),
                    (["--host-port", "7099", "--device", "127.0.0.1", "test", "--help"], "host-port_space"),
                    (["--host-port=7099", "--device", "127.0.0.1", "test", "--help"], "host-port_equals"),
                ]
            )
        for argv, variant in argv_variants:
            proc = subprocess.run(
                prefix + argv,
                capture_output=True,
                text=True,
                timeout=probe_timeout,
                check=False,
            )
            combined = (proc.stdout or "") + (proc.stderr or "")
            token = argv[0].split("=")[0]
            if not _argv_rejects_option(combined, token):
                help_test = combined
                supported = True
                detail = f"functional_argv:{variant}"
                detection_source = "cli_argv"
                break
            if _quick_probe_mode():
                detail = "argv_rejected_quick_probe"
                break

        if not supported and detail == "not_probed":
            detail = "argv_rejected_all_variants"
    except (OSError, subprocess.TimeoutExpired) as e:
        supported = False
        detail = f"probe_error:{e}"

    if not supported and _help_mentions_driver_port(help_global):
        detail = "help_only_global_no_argv"
    if not supported and _help_mentions_driver_port(help_test_cmd):
        detail = "help_only_maestro_test_help_no_argv"
    if not supported and _help_mentions_driver_port(help_test):
        detail = "help_only_test_argv_no_functional"
    if not supported and internal_api:
        detail = f"{detail};internal_driverHostPort_api_unexposed"

    cand = MaestroInstallCandidate(
        label=label,
        bin_dir=bin_dir,
        app_home=app_home.resolve(),
        launcher=launcher.resolve(),
        cli_version=version,
        driver_host_port_supported=supported,
        probe_detail=f"{detail} source={detection_source}",
        lib_mtime=_lib_mtime(app_home),
        internal_driver_port_api=internal_api,
    )
    print(
        f"[ATP] maestro_install_probe end label={label} cli={version} driver_port="
        f"{'yes' if supported else 'no'} elapsed_sec={time.time() - t0:.1f}",
        flush=True,
    )
    return cand


def _extra_candidate_paths() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    raw = (os.environ.get("ATP_MAESTRO_HOME_CANDIDATES") or "").strip()
    for part in re.split(r"[;]", raw):
        part = part.strip().strip('"')
        if part:
            out.append(("env_candidate", Path(part)))
    parallel_home = (os.environ.get("ATP_MAESTRO_PARALLEL_HOME") or "").strip().strip('"')
    if parallel_home:
        out.append(("parallel_home", Path(parallel_home)))
    default_parallel = Path(r"C:\Tools\maestro-parallel\bin")
    alt_parallel = Path(r"C:\Tools\maestro-parallel\maestro\bin")
    if default_parallel.is_dir():
        out.append(("default_parallel", default_parallel))
    elif alt_parallel.is_dir():
        out.append(("default_parallel", alt_parallel))
    return out


def _discover_bin_dirs(maestro_cmd: str | None = None) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(label: str, path: Path) -> None:
        try:
            key = str(path.resolve()).lower()
        except OSError:
            return
        if key in seen:
            return
        seen.add(key)
        found.append((label, path))

    mh = (os.environ.get("MAESTRO_HOME") or "").strip().strip('"')
    if mh:
        add("MAESTRO_HOME", Path(mh))

    if maestro_cmd:
        p = Path(maestro_cmd.strip().strip('"'))
        if p.is_file():
            add("maestro_cmd", p.parent)

    for label, path in _extra_candidate_paths():
        add(label, path)

    which = shutil.which("maestro.bat") or shutil.which("maestro.cmd")
    if which:
        add("PATH_where", Path(which).parent)

    scan_mode = (os.environ.get("ATP_MAESTRO_INSTALL_SCAN") or "quick").strip().lower()
    if scan_mode in ("full", "deep", "1", "true", "yes", "on"):
        if os.name == "nt":
            for base in (
                Path(os.environ.get("USERPROFILE", "")) / "maestro",
                Path(r"C:\Tools"),
                Path(r"C:\Program Files"),
                Path(r"C:\Program Files (x86)"),
            ):
                if not base.is_dir():
                    continue
                try:
                    for bat in base.rglob("maestro.bat"):
                        if bat.parent.name.lower() == "bin":
                            add(f"scan:{bat.parent.parent.name}", bat.parent)
                except OSError:
                    continue
    elif os.name == "nt":
        user_maestro = Path(os.environ.get("USERPROFILE", "")) / "maestro" / "maestro" / "bin"
        if user_maestro.is_dir():
            add("scan:user_maestro_default", user_maestro)

    return found


def discover_maestro_installs(*, maestro_cmd: str | None = None) -> list[MaestroInstallCandidate]:
    print("[ATP] maestro_install_discovery begin", flush=True)
    bin_dirs = _discover_bin_dirs(maestro_cmd)
    # Fast path: prefer parallel home first when Jenkins pins an old MAESTRO_HOME.
    parallel = (os.environ.get("ATP_MAESTRO_PARALLEL_HOME") or "").strip().strip('"')
    if parallel and _quick_probe_mode():
        ph = Path(parallel).resolve()
        bin_dirs = [("parallel_home", ph)] + [
            (lb, p) for lb, p in bin_dirs if str(p.resolve()).lower() != str(ph).lower()
        ]
    installs: list[MaestroInstallCandidate] = []
    for label, bin_dir in bin_dirs:
        cand = probe_install(bin_dir, label=label)
        if cand is not None:
            installs.append(cand)
    installs.sort(
        key=lambda c: (
            0 if c.driver_host_port_supported else 1,
            tuple(-x for x in _parse_cli_version_tuple(c.cli_version)),
            -(c.lib_mtime or 0),
        )
    )
    print(f"[ATP] maestro_install_discovery end count={len(installs)}", flush=True)
    return installs


def log_install_audit(installs: list[MaestroInstallCandidate]) -> None:
    print("[ATP] maestro_install_audit begin", flush=True)
    if not installs:
        print("  (no Maestro installations discovered)", flush=True)
    for inst in installs:
        print(inst.log_line(), flush=True)
        print(f"    app_home={inst.app_home} launcher={inst.launcher}", flush=True)
    print("[ATP] maestro_install_audit end", flush=True)


def _prefer_latest_install() -> bool:
    raw = (os.environ.get("ATP_MAESTRO_PREFER_LATEST") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _probe_parallel_home_if_valid() -> MaestroInstallCandidate | None:
    parallel = (os.environ.get("ATP_MAESTRO_PARALLEL_HOME") or "").strip().strip('"')
    if not parallel:
        default = Path(r"C:\Tools\maestro-parallel\bin")
        if default.is_dir():
            parallel = str(default)
        else:
            return None
    p = Path(parallel)
    if not p.is_dir():
        print(f"[ATP] maestro_parallel_home_invalid path={parallel} reason=not_a_directory", flush=True)
        return None
    cand = probe_install(p, label="parallel_home")
    if cand is None:
        print(f"[ATP] maestro_parallel_home_invalid path={parallel} reason=probe_failed", flush=True)
    return cand


def _newest_install(installs: list[MaestroInstallCandidate]) -> MaestroInstallCandidate | None:
    if not installs:
        return None
    return max(
        installs,
        key=lambda c: (_parse_cli_version_tuple(c.cli_version), c.lib_mtime or 0),
    )


def _apply_maestro_home_selection(selected: MaestroInstallCandidate, *, inherited: str) -> None:
    os.environ["MAESTRO_HOME"] = str(selected.bin_dir)
    os.environ["ATP_MAESTRO_SELECTED_INSTALL"] = selected.label
    if inherited and inherited.strip().strip('"').lower() != str(selected.bin_dir).lower():
        print(
            f"[ATP] maestro_home_override inherited={inherited.strip()} "
            f"selected={selected.bin_dir} label={selected.label} "
            f"cli={selected.cli_version} driver_port="
            f"{'yes' if selected.driver_host_port_supported else 'no'}",
            flush=True,
        )
    else:
        print(
            f"[ATP] maestro_home_selected={selected.bin_dir} "
            f"(label={selected.label} cli={selected.cli_version} "
            f"driver_port={'yes' if selected.driver_host_port_supported else 'no'})",
            flush=True,
        )


def resolve_maestro_for_parallel(
    *,
    maestro_cmd: str | None,
    device_count: int,
    prefer_parallel: bool = True,
) -> MaestroInstallCandidate | None:
    """
    Select Maestro install and set MAESTRO_HOME for this process.

    Priority (device count does not pin stale MAESTRO_HOME):
      a) ATP_MAESTRO_PARALLEL_HOME / C:\\Tools\\maestro-parallel\\bin when valid
      b) newest discovered CLI by version / lib mtime (when ATP_MAESTRO_PREFER_LATEST=1)
      c) inherited MAESTRO_HOME only as last resort
    """
    inherited = (os.environ.get("MAESTRO_HOME") or "").strip().strip('"')
    print("[ATP] maestro_capability_resolution begin", flush=True)
    installs = discover_maestro_installs(maestro_cmd=maestro_cmd)
    log_install_audit(installs)
    if not installs:
        return None

    selected: MaestroInstallCandidate | None = None
    if _prefer_latest_install():
        parallel_home = _probe_parallel_home_if_valid()
        if parallel_home is not None:
            selected = parallel_home
            _set_selection_reason("forced_parallel_home")
        else:
            selected = _newest_install(installs)
            if selected is not None:
                _set_selection_reason("newest_discovered_cli")
            elif inherited:
                for inst in installs:
                    if str(inst.bin_dir).lower() == inherited.lower():
                        selected = inst
                        _set_selection_reason("maestro_home_fallback")
                        break
    else:
        _set_selection_reason("prefer_latest_disabled")
        if inherited:
            for inst in installs:
                if str(inst.bin_dir).lower() == inherited.lower():
                    selected = inst
                    break
        if selected is None:
            selected = installs[0]

    if selected is None:
        selected = installs[0]
        _set_selection_reason("first_discovered")

    _apply_maestro_home_selection(selected, inherited=inherited)
    print(f"[ATP] maestro_selection_reason={get_maestro_selection_reason()}", flush=True)
    print(f"[ATP] maestro_selected_version={selected.cli_version}", flush=True)

    parallel_capable = [i for i in installs if i.driver_host_port_supported]
    if device_count > 1 and prefer_parallel and parallel_capable:
        if selected.driver_host_port_supported:
            print(
                "[ATP] maestro_parallel_ready driver_port_supported=true native_parallel=1",
                flush=True,
            )
        else:
            print(
                "[ATP] maestro_parallel_blocker Installed Maestro lacks --driver-host-port. "
                f"Using CLI {selected.cli_version} at {selected.bin_dir}. "
                "Run: python scripts/install_maestro_parallel.py --target C:\\Tools\\maestro-parallel "
                "or install a build with PR #2821.",
                flush=True,
            )
    return selected
