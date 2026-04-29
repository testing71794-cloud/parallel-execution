#!/usr/bin/env python3
"""
Jenkins CPS helper: run / validate / excel for one ATP folder in one process.
Keeps Jenkinsfile small (avoids WorkflowScript MethodTooLargeException).

Does not replace run_atp_testcase_flows.ps1 logic — only invokes existing scripts.
Suite ids match run_atp_testcase_flows.ps1 Get-AtpSuiteId(folder).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def folder_to_suite_id(folder: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9]+", "_", folder.strip())
    t = t.strip("_").lower()
    if not t:
        t = "unknown"
    return f"atp_{t}"


def touch_flag(name: str) -> None:
    (REPO / name).write_text("1\n", encoding="utf-8")


def cmd_run(folder: str, app: str, clear_state: str, maestro_cmd: str) -> int:
    sid = folder_to_suite_id(folder)
    bat = REPO / "scripts" / "run_atp_testcase_flows.bat"
    p = subprocess.run(
        ["cmd.exe", "/c", "call", str(bat), app, clear_state, maestro_cmd, folder],
        cwd=str(REPO),
    )
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
    p = subprocess.run(
        [
            py,
            str(REPO / "scripts" / "generate_excel_report.py"),
            str(REPO / "status"),
            str(out_dir),
            sid,
            label,
            "--skip-if-empty",
        ],
        cwd=str(REPO),
    )
    if p.returncode != 0:
        touch_flag(f"{sid}_report_failed.flag")
    return 0


def cmd_all(folder: str, app: str, clear_state: str, maestro_cmd: str) -> int:
    """One Jenkins stage per folder: run → validate → excel (shrinks CPS bytecode vs 3 stages)."""
    sid = folder_to_suite_id(folder)
    print(f"[jenkins_atp_stage] === ATP folder={folder!r} suite={sid!r} ===")
    rc_run = cmd_run(folder, app, clear_state, maestro_cmd)
    cmd_validate(sid)
    cmd_excel(folder)
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
