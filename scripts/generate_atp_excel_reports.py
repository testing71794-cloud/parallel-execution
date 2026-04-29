#!/usr/bin/env python3
"""
Merge ATP testcase rows into build-summary/final_execution_report.xlsx via generate_excel_report.py
per suite id (written by run_atp_testcase_flows.ps1 as build-summary/atp_suite_labels.json).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO
    labels_path = root / "build-summary" / "atp_suite_labels.json"
    if not labels_path.is_file():
        print("[ATP Excel] No atp_suite_labels.json — ATP skipped or no labeled suites.")
        return 0
    try:
        data = json.loads(labels_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ATP Excel] Invalid JSON in {labels_path}: {exc}", file=sys.stderr)
        return 1
    if not isinstance(data, dict) or not data:
        print("[ATP Excel] Empty labels — nothing to generate.")
        return 0

    script = REPO / "scripts" / "generate_excel_report.py"
    py = sys.executable
    rc = 0
    for suite_id_raw, label in sorted(data.items(), key=lambda x: str(x[0])):
        sid = str(suite_id_raw).strip().lower()
        lab = str(label).strip()
        out_dir = root / "reports" / f"{sid}_summary"
        cmd = [
            py,
            str(script),
            str(root / "status"),
            str(out_dir),
            sid,
            lab,
        ]
        print(f"[ATP Excel] suite={sid!r} label={lab!r}")
        p = subprocess.run(cmd, cwd=str(root))
        if p.returncode != 0:
            rc = p.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
