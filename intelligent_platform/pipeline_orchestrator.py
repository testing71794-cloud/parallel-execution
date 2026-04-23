"""
Single entry point: collect artifacts → parse → AI analyze → cluster → report → email text.

Does NOT run Maestro (Jenkins / local runners still own execution).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from . import config
from .ai_failure_analyzer import analyze_failure
from .email_enhancer import build_email_summary
from .failure_clusterer import cluster_failures
from .failure_parser import collect_failures_from_workspace, parse_failures
from .report_generator import generate_report

logger = logging.getLogger("intelligent_platform")


def _setup_logging(build_summary: Path) -> None:
    build_summary.mkdir(parents=True, exist_ok=True)
    log_path = build_summary / "intelligent_platform.log"
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt))
        handlers.append(fh)
    except OSError as e:
        print(f"Could not open log file {log_path}: {e}", file=sys.stderr)
    logging.basicConfig(level=logging.INFO if not config.DEBUG_MODE else logging.DEBUG, format=fmt, handlers=handlers)
    logger.info("Logging initialized; log file: %s", log_path)


def _count_status(root: Path) -> tuple[int, int, int]:
    """Total / passed / failed from status/*.txt"""
    status_dir = root / "status"
    total = passed = failed = 0
    if not status_dir.is_dir():
        return 0, 0, 0
    for p in status_dir.glob("*.txt"):
        data = {}
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip().lower()] = v.strip()
        except OSError:
            continue
        st = (data.get("status") or "").upper()
        if st == "RUNNING":
            continue
        total += 1
        if st == "PASS":
            passed += 1
        else:
            failed += 1
    return total, passed, failed


def load_test_artifacts(root: Path) -> list[dict[str, Any]]:
    """Collect structured failures from workspace (logs, JUnit, status)."""
    rows = collect_failures_from_workspace(root)
    logger.info("Collected %s raw failure row(s)", len(rows))
    return rows


def run_pipeline(workspace: Path | None = None) -> dict[str, Any]:
    """
    End-to-end intelligence pipeline. Returns JSON-serializable result summary.
    """
    root = workspace or config.workspace_root()
    build_summary = root / "build-summary"
    _setup_logging(build_summary)
    debug_dir = build_summary / "debug"
    if config.DEBUG_MODE:
        debug_dir.mkdir(parents=True, exist_ok=True)
        logger.info("DEBUG_MODE: intermediate outputs under %s", debug_dir)

    total, passed, failed = _count_status(root)
    logger.info("Status snapshot: total=%s passed=%s failed=%s", total, passed, failed)

    raw_failures = load_test_artifacts(root)
    if config.DEBUG_MODE:
        (debug_dir / "01_parsed_failures.json").write_text(
            json.dumps(raw_failures, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if not raw_failures:
        msg = "No structured failures found (nothing to analyze)."
        logger.info(msg)
        out = {
            "ok": True,
            "message": msg,
            "analyzed": [],
            "clusters": [],
        }
        (build_summary / "intelligence_result.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return out

    analyzed: list[dict[str, Any]] = []
    for f in raw_failures:
        try:
            ai = analyze_failure(f)
            merged: dict[str, Any] = {
                **f,
                "category": ai.get("category", "assertion"),
                "root_cause": ai.get("root_cause", ""),
                "confidence": float(ai.get("confidence", 0.0)),
                "suggestion": ai.get("suggestion", ""),
                "is_test_issue": bool(ai.get("is_test_issue", True)),
            }
            analyzed.append(merged)
            logger.info("Analyzed: %s", merged.get("test_name", "")[:80])
        except Exception as e:
            logger.exception("Per-failure analysis error (continuing): %s", e)
            analyzed.append(
                {
                    **f,
                    "category": "assertion",
                    "root_cause": f"Analyzer error: {e}",
                    "confidence": 0.0,
                    "suggestion": "Inspect raw log; re-run with INTELLIGENT_PLATFORM_DEBUG=1",
                    "is_test_issue": True,
                }
            )

    if config.DEBUG_MODE:
        (debug_dir / "02_analyzed.json").write_text(
            json.dumps(analyzed, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    cluster_rows, per_ids = cluster_failures(analyzed)
    for i, row in enumerate(analyzed):
        row["cluster_id"] = per_ids[i] if i < len(per_ids) else "CLUSTER_?"

    if config.DEBUG_MODE:
        (debug_dir / "03_clusters.json").write_text(
            json.dumps(cluster_rows, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    xlsx, summ = generate_report(analyzed, cluster_rows, build_summary)

    email_text = build_email_summary(
        analyzed, cluster_rows, total=total, passed=passed, failed=failed
    )
    if not config.SKIP_EMAIL_ARTIFACTS:
        failed_path = build_summary / "failed_summary.txt"
        try:
            failed_path.write_text(email_text, encoding="utf-8")
            logger.info("Wrote %s (for email stage)", failed_path)
        except OSError as e:
            logger.error("Could not write failed_summary.txt: %s", e)
    if config.DEBUG_MODE and config.SKIP_EMAIL_ARTIFACTS:
        (debug_dir / "04_email.txt").write_text(email_text, encoding="utf-8")

    result = {
        "ok": True,
        "excel": str(xlsx),
        "summary_json": str(summ),
        "analyzed": analyzed,
        "clusters": cluster_rows,
        "counts": {"total": total, "passed": passed, "failed": failed},
    }
    (build_summary / "intelligence_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    logger.info("Intelligence pipeline complete")
    return result


def main() -> int:
    """CLI entry: python -m intelligent_platform [workspace]"""
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        ws = Path(sys.argv[1]).resolve()
    else:
        ws = config.workspace_root()
    run_pipeline(ws)
    return 0


# Docstring example matches requested shape (orchestrates but does not execute Maestro here)
def run_pipeline_example():
    # logs = run_maestro_tests()  # owned by Jenkins / PS1 runners
    # failures = parse_failures(logs)  # use load_test_artifacts in production
    # ...
    return run_pipeline()
