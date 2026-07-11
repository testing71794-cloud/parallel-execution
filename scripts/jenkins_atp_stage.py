#!/usr/bin/env python3
"""
Jenkins CPS helper: run / validate / excel for one ATP folder in one process.
Keeps Jenkinsfile small (avoids WorkflowScript MethodTooLargeException).

Does not replace run_atp_testcase_flows.ps1 for manual runs — Jenkins ``cmd_run`` uses
``python -m execution.atp_jenkins_orchestrator`` (blocking Stack A; same reports/status as ``run_one_flow_on_device.bat``).
Suite ids match run_atp_testcase_flows.ps1 Get-AtpSuiteId(folder).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORCHESTRATOR_MODULE = "execution.atp_jenkins_orchestrator"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from execution.atp_folder_paths import discover_atp_yaml_files, resolve_atp_subfolder  # noqa: E402
from execution.subprocess_launch import log_subprocess_launch, windows_cmd_bat_argv  # noqa: E402


def folder_to_suite_id(folder: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "_", folder.strip())
    t = t.strip("_").lower()
    if not t:
        t = "unknown"
    return f"atp_{t}"


def touch_flag(name: str) -> None:
    (REPO / name).write_text("1\n", encoding="utf-8")


def _refresh_devices_on_this_agent(repo: Path) -> None:
    """
    Re-run adb device discovery on the current Windows agent before Maestro.
    Hybrid: Detect Connected Devices may run on a different executor than ATP stages.
    """
    if os.environ.get("ATP_REFRESH_DEVICES_BEFORE_RUN", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_REFRESH_DEVICES_BEFORE_RUN=0 — skip device refresh", flush=True)
        return
    bat = repo / "scripts" / "windows_agent" / "list_devices.bat"
    if not bat.is_file():
        bat = repo / "scripts" / "list_devices.bat"
    if not bat.is_file():
        return
    print(
        f"[jenkins_atp_stage] refreshing detected_devices.txt on this agent ({bat.name})",
        flush=True,
    )
    env = os.environ.copy()
    # Avoid cmd.exe splitting workspace paths if a prior stage set MAESTRO_OPTS with -Duser.home=...
    for _k in (
        "MAESTRO_OPTS",
        "ATP_JAVA_USER_HOME",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS",
    ):
        env.pop(_k, None)
    cmd = windows_cmd_bat_argv(bat, str(repo.resolve()))
    log_subprocess_launch(cmd, cwd=repo.resolve(), shell=False, label="list_devices")
    subprocess.run(
        cmd,
        cwd=str(repo.resolve()),
        env=env,
        check=False,
        shell=False,
    )


def _log_orchestrator_fingerprint(repo: Path) -> None:
    orch_py = repo / "execution" / "atp_jenkins_orchestrator.py"
    print(f"[jenkins_atp_stage] orchestrator_module={ORCHESTRATOR_MODULE}", flush=True)
    print(f"[jenkins_atp_stage] orchestrator_path={orch_py}", flush=True)
    if orch_py.is_file():
        print(f"[jenkins_atp_stage] orchestrator_mtime={orch_py.stat().st_mtime}", flush=True)
    rev_file = repo / "execution" / "ORCHESTRATOR_REV.txt"
    if rev_file.is_file():
        rev = rev_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0].strip()
        if rev:
            print(f"[jenkins_atp_stage] orchestrator_rev={rev}", flush=True)


def _log_folder_discovery(folder_arg: str, resolved: str) -> None:
    print(f"[jenkins_atp_stage] workspace={REPO.resolve()}", flush=True)
    print(f"[jenkins_atp_stage] folder_arg={folder_arg!r} resolved_folder={resolved!r}", flush=True)
    flows = discover_atp_yaml_files(REPO, resolved or folder_arg, exclude_subflows=True)
    if flows:
        print(f"[jenkins_atp_stage] preflight: {len(flows)} yaml test file(s) to run:", flush=True)
        for p in flows:
            try:
                rel = p.resolve().relative_to(REPO.resolve())
            except ValueError:
                rel = p
            print(f"[jenkins_atp_stage]   - {rel}", flush=True)
    else:
        print("[jenkins_atp_stage] preflight: 0 yaml test files (stage will fail)", flush=True)


def _validate_maestro_yaml_preflight() -> int:
    if os.environ.get("ATP_VALIDATE_MAESTRO_YAML", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return 0
    validator = REPO / "scripts" / "validate_maestro_yaml.py"
    atp_root = REPO / "ATP TestCase Flows"
    if not validator.is_file():
        print("[jenkins_atp_stage] validate_maestro_yaml: script missing — skip", flush=True)
        return 0
    if not atp_root.is_dir():
        return 0
    cmd = [sys.executable, str(validator), str(atp_root)]
    log_subprocess_launch(cmd, cwd=REPO, shell=False, label="validate_maestro_yaml")
    proc = subprocess.run(cmd, cwd=str(REPO), check=False)
    if proc.returncode != 0:
        print("[jenkins_atp_stage] ERROR: Maestro YAML validation failed", flush=True)
    return proc.returncode


def _is_gallery_folder(folder: str) -> bool:
    resolved = resolve_atp_subfolder(REPO, folder)
    key = (resolved or folder or "").strip().lower()
    return key == "gallery"


def _is_editing_folder(folder: str) -> bool:
    resolved = resolve_atp_subfolder(REPO, folder)
    key = (resolved or folder or "").strip().lower()
    return key == "editing"


def _is_printing_folder(folder: str) -> bool:
    resolved = resolve_atp_subfolder(REPO, folder)
    key = (resolved or folder or "").strip().lower()
    return key == "printing"


def _prepend_path(*dirs: Path) -> None:
    cur = os.environ.get("PATH", "")
    parts = [str(d) for d in dirs if d.is_dir()]
    if not parts:
        return
    prefix = os.pathsep.join(parts)
    if prefix.lower() not in cur.lower():
        os.environ["PATH"] = prefix + os.pathsep + cur


def _resolve_npm_executable() -> str | None:
    """Windows Jenkins agents need npm.cmd — bare 'npm' is not a CreateProcess executable."""
    candidates: list[Path] = []
    node_home = os.environ.get("NODE_HOME", "").strip().strip('"')
    if node_home:
        candidates.append(Path(node_home) / ("npm.cmd" if os.name == "nt" else "npm"))
    candidates.append(Path(r"C:\Program Files\nodejs\npm.cmd"))
    candidates.append(Path(r"C:\Program Files\nodejs\npm"))
    for path in candidates:
        if path.is_file():
            return str(path.resolve())
    found = shutil.which("npm")
    if found:
        return found
    if os.name == "nt":
        for name in ("npm.cmd", "npm.exe", "npm"):
            found = shutil.which(name)
            if found:
                return found
    return None


def _prepare_gallery_appium(folder: str) -> None:
    """Node/Appium deps for GA_05/GA_06 real W3C pinch when Jenkins runs gallery suite."""
    if not _is_gallery_folder(folder):
        return
    if os.environ.get("ATP_GALLERY_APPIUM_PINCH", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_GALLERY_APPIUM_PINCH=0 — GA_05/GA_06 use Maestro-only yaml", flush=True)
        return

    os.environ.setdefault("ATP_GALLERY_APPIUM_PINCH", "1")
    os.environ.setdefault("ATP_REQUIRE_PINCH_VISION", "1")
    os.environ.setdefault("GALLERY_PINCH", "1")
    os.environ.setdefault("PINCH_STYLE", "diagonal")
    os.environ.setdefault("NPM_GLOBAL", r"C:\Tools\npm-global")
    os.environ.setdefault("APPIUM_BIN", r"C:\Tools\npm-global\appium.cmd")

    _prepend_path(
        Path(r"C:\Program Files\nodejs"),
        Path(r"C:\Tools\npm-global"),
        Path.home() / "AppData" / "Roaming" / "npm",
    )

    mod = REPO / "automation" / "appium-gestures"
    pkg = mod / "package.json"
    wdio = mod / "node_modules" / "webdriverio"
    if pkg.is_file() and not wdio.is_dir():
        npm = _resolve_npm_executable()
        if not npm:
            print(
                "[jenkins_atp_stage] WARN: npm not found — skip appium-gestures npm install; "
                "install Node.js on agent or set NODE_HOME (GA_05/GA_06 Appium pinch may fail)",
                flush=True,
            )
        else:
            cmd = [npm, "install", "--no-fund", "--no-audit"]
            print(f"[jenkins_atp_stage] gallery Appium: npm install in {mod} via {npm}", flush=True)
            log_subprocess_launch(cmd, cwd=mod, shell=False, label="gallery_appium_npm_install")
            try:
                subprocess.run(cmd, cwd=str(mod), check=False, shell=False)
            except OSError as exc:
                print(f"[jenkins_atp_stage] WARN: npm install failed to start: {exc}", flush=True)
    print(
        "[jenkins_atp_stage] gallery Appium pinch: "
        f"ATP_GALLERY_APPIUM_PINCH={os.environ.get('ATP_GALLERY_APPIUM_PINCH', '')} "
        f"GALLERY_PINCH={os.environ.get('GALLERY_PINCH', '')} "
        f"PINCH_STYLE={os.environ.get('PINCH_STYLE', '')} "
        f"npm={_resolve_npm_executable() or 'not-found'}",
        flush=True,
    )


def _prepare_gallery_openrouter(folder: str) -> None:
    """GraalJS host access + local verify server for GA_02 OpenRouter vision verify."""
    if not _is_gallery_folder(folder):
        return
    import importlib.util

    mod_path = REPO / "scripts" / "ensure_maestro_verify_server.py"
    spec = importlib.util.spec_from_file_location("ensure_maestro_verify_server", mod_path)
    if spec is None or spec.loader is None:
        print(f"[jenkins_atp_stage] WARN: cannot load {mod_path}", flush=True)
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.apply_maestro_graaljs_env()
    print(
        "[jenkins_atp_stage] gallery OpenRouter: "
        f"MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS={os.environ.get('MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS', '')} "
        f"OPENROUTER_MODEL_VISION={os.environ.get('OPENROUTER_MODEL_VISION', '')}",
        flush=True,
    )
    if os.environ.get("ATP_GALLERY_VERIFY_SERVER", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_GALLERY_VERIFY_SERVER=0 — skip verify server", flush=True)
        return
    if not mod.ensure_verify_server(REPO):
        print(
            "[jenkins_atp_stage] WARN: verify server not ready; GA_02 may still use GraalJS adb capture",
            flush=True,
        )


def _apply_editing_ci_defaults(folder: str) -> None:
    """Set editing-stage defaults before flow discovery (must run before preflight log)."""
    if not _is_editing_folder(folder):
        return
    os.environ.setdefault(
        "ATP_FLOW_EXCLUDE",
        "ED_Q,"
        "ED_02 - Apply,"
        "ED_03 - Frames,"
        "ED_03B,ED_03C,ED_03D,ED_03E,ED_03F,ED_03G,ED_03H,"
        "ED_04 - Stickers,"
        "ED_04B,ED_04C,ED_04D,ED_04E,ED_04F,ED_04G,ED_04H",
    )
    os.environ.setdefault("EDITING_VERIFY_SOFT", "1")
    os.environ.setdefault("OPENROUTER_VISION_TIMEOUT_SEC", "25")
    os.environ.setdefault("OPENROUTER_VISION_MAX_ROUNDS", "1")
    # Vision fallbacks: intelligent_platform.config.openrouter_vision_model_chain()


def _is_barbie_folder(folder: str) -> bool:
    resolved = resolve_atp_subfolder(REPO, folder)
    key = (resolved or folder or "").strip().lower()
    return key == "barbie"


def _apply_barbie_ci_defaults(folder: str) -> None:
    """Set Barbie-stage defaults before flow discovery (must run before preflight log)."""
    if not _is_barbie_folder(folder):
        return
    os.environ.setdefault("EDITING_VERIFY_SOFT", "1")
    os.environ.setdefault("OPENROUTER_VISION_TIMEOUT_SEC", "25")
    os.environ.setdefault("OPENROUTER_VISION_MAX_ROUNDS", "1")


def _apply_printing_ci_defaults(folder: str) -> None:
    """Set printing-stage defaults before flow discovery (must run before preflight log)."""
    if not _is_printing_folder(folder):
        return
    os.environ.setdefault("EDITING_VERIFY_SOFT", "1")
    os.environ.setdefault("OPENROUTER_VISION_TIMEOUT_SEC", "25")
    os.environ.setdefault("OPENROUTER_VISION_MAX_ROUNDS", "1")


def _prepare_editing_openrouter(folder: str) -> None:
    """GraalJS host access + editing verify server for ED_* OpenRouter vision verify."""
    if not _is_editing_folder(folder):
        return
    import importlib.util

    mod_path = REPO / "scripts" / "ensure_editing_verify_server.py"
    spec = importlib.util.spec_from_file_location("ensure_editing_verify_server", mod_path)
    if spec is None or spec.loader is None:
        print(f"[jenkins_atp_stage] WARN: cannot load {mod_path}", flush=True)
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.apply_editing_openrouter_env()
    _apply_editing_ci_defaults(folder)
    print(
        "[jenkins_atp_stage] editing OpenRouter: "
        f"MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS={os.environ.get('MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS', '')} "
        f"OPENROUTER_MODEL_VISION={os.environ.get('OPENROUTER_MODEL_VISION', '')} "
        f"EDITING_VERIFY_PORT={os.environ.get('EDITING_VERIFY_PORT', '8767')} "
        f"EDITING_VERIFY_SOFT={os.environ.get('EDITING_VERIFY_SOFT', '')} "
        f"ATP_FLOW_EXCLUDE={os.environ.get('ATP_FLOW_EXCLUDE', '')}",
        flush=True,
    )
    if os.environ.get("ATP_EDITING_VERIFY_SERVER", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_EDITING_VERIFY_SERVER=0 — skip editing verify server", flush=True)
        return
    if not mod.ensure_editing_verify_server(REPO):
        print(
            "[jenkins_atp_stage] WARN: editing verify server not ready; ED_* may use GraalJS direct OpenRouter",
            flush=True,
        )


def _prepare_printing_openrouter(folder: str) -> None:
    """GraalJS host access + shared verify server for PR_* OpenRouter vision verify."""
    if not _is_printing_folder(folder):
        return
    import importlib.util

    mod_path = REPO / "scripts" / "ensure_editing_verify_server.py"
    spec = importlib.util.spec_from_file_location("ensure_editing_verify_server", mod_path)
    if spec is None or spec.loader is None:
        print(f"[jenkins_atp_stage] WARN: cannot load {mod_path}", flush=True)
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.apply_editing_openrouter_env()
    _apply_printing_ci_defaults(folder)
    print(
        "[jenkins_atp_stage] printing OpenRouter: "
        f"MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS={os.environ.get('MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS', '')} "
        f"OPENROUTER_MODEL_VISION={os.environ.get('OPENROUTER_MODEL_VISION', '')} "
        f"EDITING_VERIFY_PORT={os.environ.get('EDITING_VERIFY_PORT', '8767')} "
        f"EDITING_VERIFY_SOFT={os.environ.get('EDITING_VERIFY_SOFT', '')} "
        f"OPENROUTER_VISION_TIMEOUT_SEC={os.environ.get('OPENROUTER_VISION_TIMEOUT_SEC', '')} "
        f"OPENROUTER_VISION_MAX_ROUNDS={os.environ.get('OPENROUTER_VISION_MAX_ROUNDS', '')}",
        flush=True,
    )
    if os.environ.get("ATP_PRINTING_VERIFY_SERVER", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_PRINTING_VERIFY_SERVER=0 — skip printing verify server", flush=True)
        return
    if not mod.ensure_editing_verify_server(REPO):
        print(
            "[jenkins_atp_stage] WARN: verify server not ready; PR_* may use GraalJS direct OpenRouter",
            flush=True,
        )


def _prepare_barbie_openrouter(folder: str) -> None:
    """GraalJS host access + shared verify server for BA_* OpenRouter vision verify."""
    if not _is_barbie_folder(folder):
        return
    import importlib.util

    mod_path = REPO / "scripts" / "ensure_editing_verify_server.py"
    spec = importlib.util.spec_from_file_location("ensure_editing_verify_server", mod_path)
    if spec is None or spec.loader is None:
        print(f"[jenkins_atp_stage] WARN: cannot load {mod_path}", flush=True)
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.apply_editing_openrouter_env()
    _apply_barbie_ci_defaults(folder)
    print(
        "[jenkins_atp_stage] barbie OpenRouter: "
        f"MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS={os.environ.get('MAESTRO_CLI_DANGEROUS_GRAALJS_ALLOW_HOST_ACCESS', '')} "
        f"OPENROUTER_MODEL_VISION={os.environ.get('OPENROUTER_MODEL_VISION', '')} "
        f"EDITING_VERIFY_PORT={os.environ.get('EDITING_VERIFY_PORT', '8767')} "
        f"EDITING_VERIFY_SOFT={os.environ.get('EDITING_VERIFY_SOFT', '')} "
        f"OPENROUTER_VISION_TIMEOUT_SEC={os.environ.get('OPENROUTER_VISION_TIMEOUT_SEC', '')} "
        f"OPENROUTER_VISION_MAX_ROUNDS={os.environ.get('OPENROUTER_VISION_MAX_ROUNDS', '')}",
        flush=True,
    )
    if os.environ.get("ATP_BARBIE_VERIFY_SERVER", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        print("[jenkins_atp_stage] ATP_BARBIE_VERIFY_SERVER=0 — skip barbie verify server", flush=True)
        return
    if not mod.ensure_editing_verify_server(REPO):
        print(
            "[jenkins_atp_stage] WARN: verify server not ready; BA_* may use GraalJS direct OpenRouter",
            flush=True,
        )


def cmd_run(folder: str, app: str, clear_state: str, maestro_cmd: str) -> int:
    resolved = resolve_atp_subfolder(REPO, folder)
    sid = folder_to_suite_id(resolved or folder)
    _apply_editing_ci_defaults(folder)
    _apply_printing_ci_defaults(folder)
    _apply_barbie_ci_defaults(folder)
    _log_folder_discovery(folder, resolved)
    yaml_rc = _validate_maestro_yaml_preflight()
    if yaml_rc != 0:
        touch_flag(f"{sid}_failed.flag")
        return yaml_rc
    _prepare_gallery_openrouter(folder)
    _prepare_gallery_appium(folder)
    _prepare_editing_openrouter(folder)
    _prepare_printing_openrouter(folder)
    _prepare_barbie_openrouter(folder)
    _refresh_devices_on_this_agent(REPO)
    _log_orchestrator_fingerprint(REPO)
    maestro_argv = [
        sys.executable,
        "-m",
        ORCHESTRATOR_MODULE,
        str(REPO),
        app,
        clear_state,
        maestro_cmd,
        resolved or folder,
    ]
    if not discover_atp_yaml_files(REPO, resolved or folder, exclude_subflows=True):
        print("[jenkins_atp_stage] ERROR: no yaml test files — aborting stage", flush=True)
        touch_flag(f"{sid}_no_results.flag")
        return 1
    print(f"[jenkins_atp_stage] maestro_command={' '.join(maestro_argv)!r}", flush=True)
    # Stack A: blocking Python orchestrator (no detached PowerShell Start-Process chain).
    p = subprocess.run(maestro_argv, cwd=str(REPO))
    if p.returncode != 0:
        touch_flag(f"{sid}_failed.flag")
    return p.returncode


def cmd_validate(suite_id: str) -> int:
    """Match Jenkins bat: set *_no_results.flag on issues; step exit 0 (catchError / flags)."""
    root = REPO
    py = sys.executable
    v = subprocess.run(
        [py, str(REPO / "scripts" / "validate_suite_artifacts.py"), suite_id, str(root)],
        cwd=str(root),
    )
    if v.returncode != 0:
        touch_flag(f"{suite_id}_no_results.flag")

    status_dir = root / "status"
    rep = root / "reports" / suite_id
    st = list(status_dir.glob(f"{suite_id}__*.txt")) if status_dir.is_dir() else []
    csv = list((rep / "results").glob("*.csv")) if (rep / "results").is_dir() else []
    logs = list((rep / "logs").glob("*.log")) if (rep / "logs").is_dir() else []
    if not st or not csv or not logs:
        touch_flag(f"{suite_id}_no_results.flag")
    return 0


def cmd_excel(folder: str) -> int:
    """Per-folder Excel merge; flag on failure; exit 0 like Jenkins bat echo chain."""
    sid = folder_to_suite_id(folder)
    label = folder
    (REPO / "build-summary").mkdir(parents=True, exist_ok=True)
    out_dir = REPO / "reports" / f"{sid}_summary"
    py = sys.executable
    # Do NOT pass --skip-if-empty: failed runs may have no parsable status rows yet we still
    # must merge into final_execution_report.xlsx (generate_excel_report writes placeholder rows).
    p = subprocess.run(
        [
            py,
            str(REPO / "scripts" / "generate_excel_report.py"),
            str(REPO / "status"),
            str(out_dir),
            sid,
            label,
        ],
        cwd=str(REPO),
    )
    if p.returncode != 0:
        touch_flag(f"{sid}_report_failed.flag")
    return 0


def cmd_all(folder: str, app: str, clear_state: str, maestro_cmd: str) -> int:
    """One Jenkins stage per folder: run → validate → excel (shrinks CPS bytecode vs 3 stages)."""
    resolved = resolve_atp_subfolder(REPO, folder)
    sid = folder_to_suite_id(resolved or folder)
    print(f"[jenkins_atp_stage] === ATP folder={folder!r} resolved={resolved!r} suite={sid!r} ===", flush=True)
    print(
        f"[jenkins_atp_stage] agent_env MAESTRO_HOME={os.environ.get('MAESTRO_HOME', '')} "
        f"ATP_MAESTRO_PARALLEL_HOME={os.environ.get('ATP_MAESTRO_PARALLEL_HOME', '')} "
        f"JAVA_HOME={os.environ.get('JAVA_HOME', '')}",
        flush=True,
    )
    rc_run = cmd_run(folder, app, clear_state, maestro_cmd)
    cmd_validate(sid)
    cmd_excel(resolved or folder)
    if rc_run != 0:
        print(f"[jenkins_atp_stage] stage_status=FAILED suite={sid!r} exit={rc_run}", flush=True)
    else:
        print(f"[jenkins_atp_stage] stage_status=OK suite={sid!r}", flush=True)
    return rc_run


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "Usage: jenkins_atp_stage.py run <Folder> <APP_PACKAGE> <CLEAR_STATE> <MAESTRO_CMD>\n"
            "       jenkins_atp_stage.py validate <suite_id>\n"
            "       jenkins_atp_stage.py excel <Folder>\n"
            "       jenkins_atp_stage.py all <Folder> <APP_PACKAGE> <CLEAR_STATE> <MAESTRO_CMD>",
            file=sys.stderr,
        )
        return 2
    op = sys.argv[1].lower().strip()
    if op == "run":
        if len(sys.argv) < 6:
            print("run: need Folder APP CLEAR_STATE MAESTRO_CMD", file=sys.stderr)
            return 2
        return cmd_run(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    if op == "validate":
        if len(sys.argv) < 3:
            print("validate: need suite_id", file=sys.stderr)
            return 2
        return cmd_validate(sys.argv[2].strip().lower())
    if op == "excel":
        if len(sys.argv) < 3:
            print("excel: need Folder", file=sys.stderr)
            return 2
        return cmd_excel(sys.argv[2])
    if op == "all":
        if len(sys.argv) < 6:
            print("all: need Folder APP CLEAR_STATE MAESTRO_CMD", file=sys.stderr)
            return 2
        return cmd_all(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    print(f"Unknown op: {op}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
