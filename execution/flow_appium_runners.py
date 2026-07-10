"""Route selected Maestro ATP flows to Appium W3C pinch runners (Jenkins / run_one_flow)."""
from __future__ import annotations

from pathlib import Path

# Top-level ATP yaml stem -> repo-relative runner .bat (device serial passed as %1).
_FLOW_RUNNER_BAT: dict[str, str] = {
    "GA_05 - Pinch to zoom out": "scripts/run_ga05_real_pinch.bat",
    "GA_06 - Pinch to zoom in": "scripts/run_ga06_real_pinch.bat",
}


def resolve_appium_runner_bat(flow_path: Path, repo: Path) -> Path | None:
    """Return absolute .bat path when flow should use Appium W3C pinch instead of Maestro-only yaml."""
    rel = _FLOW_RUNNER_BAT.get((flow_path.stem or "").strip())
    if not rel:
        return None
    bat = (repo / rel).resolve()
    return bat if bat.is_file() else None
