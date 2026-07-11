"""
Camera view + capture vision analysis for the main ATP Excel automation pipeline.

Uses ai-agent/analysis rules (no Maestro YAML changes, no separate Jenkins checkbox).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AGENT = REPO / "ai-agent"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from analysis.camera_analyzer import (  # noqa: E402
    CameraAnalyzer,
    analyze_flow_from_workspace,
)


def is_camera_automation_flow(flow_name: str, suite: str = "") -> bool:
    if CameraAnalyzer.is_camera_flow(flow_name):
        return True
    return "atp_camera" in (suite or "").lower()


def analyze_camera_for_excel_row(
    *,
    flow_name: str,
    suite: str,
    device_id: str,
    status: str = "",
) -> dict[str, Any] | None:
    """Return camera view/capture analysis for one Excel/status row, or None if not a camera flow."""
    if not is_camera_automation_flow(flow_name, suite):
        return None

    analyzer = CameraAnalyzer(REPO, llm=None)
    suite_id = (suite or "atp_camera").strip() or "atp_camera"
    view, capture = analyze_flow_from_workspace(
        analyzer,
        REPO,
        suite_id=suite_id,
        flow_name=flow_name,
        device_id=device_id or "unknown",
    )

    parts = [f"View:{view.status.upper()}({view.confidence:.2f}) {view.summary}"]
    if capture.status != "skipped":
        parts.append(f"Capture:{capture.status.upper()}({capture.confidence:.2f}) {capture.summary}")

    summary = " | ".join(parts)
    st = (status or "").upper()
    if st == "PASS":
        if view.status == "fail" or capture.status == "fail":
            category = "Camera UI/Capture verification failed on PASS row"
            suggested = "Review Maestro assertions vs actual camera UI; check debug screenshots."
        else:
            category = "Camera verification"
            suggested = "—"
    elif view.status == "fail":
        category = "Camera view"
        suggested = "Verify camera opened: capture_img, flip, menu, back; grant camera permission."
    elif capture.status == "fail":
        category = "Camera capture"
        suggested = "Verify shutter tap, preview update, and thumbnail/gallery return."
    else:
        category = "Camera"
        suggested = "Inspect camera debug artifacts under reports/atp_camera/maestro-debug/."

    screenshot = view.screenshot or capture.screenshot or ""
    confidence = min(view.confidence, capture.confidence if capture.status != "skipped" else 1.0)

    return {
        "camera_view_status": view.status,
        "camera_capture_status": capture.status,
        "camera_summary": summary,
        "ai_failure_summary": summary,
        "root_cause_category": category,
        "suggested_fix": suggested,
        "ai_confidence": confidence,
        "analysis_source": "Camera vision (automation)",
        "model_used": "camera_rules",
        "screenshot_path": screenshot,
    }
