#!/usr/bin/env python3
"""
Validate that a suite (nonprinting | printing | atp_*) produced status and/or report artifacts.
Exit 0 if any expected files exist; exit 1 if the suite had no retrievable output (aligns with Jenkins *no_results.flag).
"""
from __future__ import annotations

import sys
from pathlib import Path

VALID = frozenset({"nonprinting", "printing"})


def _is_atp_suite(suite: str) -> bool:
    """ATP suites use ids like atp_camera, atp_signup_login (see run_atp_testcase_flows.ps1)."""
    return suite.startswith("atp_") and len(suite) > 4


def _collect(
    root: Path, suite: str
) -> tuple[int, int, int]:
    status_dir = root / "status"
    n_status = 0
    if status_dir.is_dir():
        n_status = len(list(status_dir.glob(f"{suite}__*.txt")))

    r = root / "reports" / suite
    n_csv = 0
    res = r / "results"
    if res.is_dir():
        n_csv = len(list(res.glob("*.csv")))
    n_log = 0
    logs = r / "logs"
    if logs.is_dir():
        n_log = len(list(logs.glob("*.log")))

    return n_status, n_csv, n_log


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/validate_suite_artifacts.py <nonprinting|printing|atp_*> <workspace_root>",
            file=sys.stderr,
        )
        return 2
    suite = sys.argv[1].strip().lower()
    if suite not in VALID and not _is_atp_suite(suite):
        print(
            f"Unknown suite: {suite!r} (expected nonprinting|printing|atp_*)",
            file=sys.stderr,
        )
        return 2
    root = Path(sys.argv[2]).resolve()
    n_status, n_csv, n_log = _collect(root, suite)
    if n_status or n_csv or n_log:
        print(
            f"OK {suite}: status={n_status} results_csv={n_csv} logs={n_log} (root={root})"
        )
        return 0
    print(f"No artifacts for suite {suite!r} under {root}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
