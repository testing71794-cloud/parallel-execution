#!/usr/bin/env python3
"""
Generate Failed Tests HTML report (only FAIL rows).

Usage:
  python scripts/generate_failed_tests_report.py
  python scripts/generate_failed_tests_report.py --out ai-agent/reports/failed_tests.html

Reads:
  - build-summary/failed_tests_summary.json (from collect_failed_artifacts.py)
  - build-summary/final_execution_report.xlsx (AI Analysis column when present)

Writes:
  - failed_tests.html (+ .json companion)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ai-agent"))
sys.path.insert(0, str(REPO / "scripts"))

from reporting.failed_tests_report import (  # noqa: E402
    load_failed_summary,
    merge_failed_rows,
    rows_from_excel_failures,
    write_failed_tests_report,
)


def _excel_rows(repo: Path) -> list[dict]:
    excel = repo / "build-summary" / "final_execution_report.xlsx"
    if not excel.is_file():
        excel = repo / "final_execution_report.xlsx"
    if not excel.is_file():
        return []
    try:
        from mailout.send_email import read_execution_table_rows

        rows, _err = read_execution_table_rows(excel)
        return rows_from_excel_failures(rows)
    except Exception as exc:  # noqa: BLE001
        print(f"[failed-tests-report] excel enrich skipped: {exc}", flush=True)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Failed Tests HTML report")
    ap.add_argument("--repo", default=str(REPO), help="Repository root")
    ap.add_argument(
        "--out",
        default="",
        help="Output HTML path (default: ai-agent/reports/failed_tests.html)",
    )
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    out = Path(args.out) if args.out else repo / "ai-agent" / "reports" / "failed_tests.html"

    # Ensure collector ran if summary missing but status exists
    summary = load_failed_summary(repo)
    if not summary:
        try:
            from collect_failed_artifacts import collect_failed_artifacts

            print("[failed-tests-report] collecting failed artifacts…", flush=True)
            collect_failed_artifacts(repo)
        except Exception as exc:  # noqa: BLE001
            print(f"[failed-tests-report] collect skipped: {exc}", flush=True)

    path = write_failed_tests_report(repo, out, excel_fail_rows=_excel_rows(repo))
    n = len(merge_failed_rows(summary_rows=load_failed_summary(repo), excel_fail_rows=_excel_rows(repo)))
    print(f"[failed-tests-report] wrote {path} failures={n}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
