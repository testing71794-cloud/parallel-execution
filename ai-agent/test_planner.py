"""Test Planner — auto-discover ATP modules (folders + YAML)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from config_loader import FEATURE_ALIASES
from models import ModulePlan

logger = logging.getLogger("ai-agent.planner")

# Preferred execution order for full regression (unknown folders appended alphabetically).
PREFERRED_ORDER = [
    "SignUp_Login",
    "Onboarding",
    "Camera",
    "Editing",
    "Collage",
    "Precut",
    "Printing",
    "Settings",
]


class TestPlanner:
    """Discovers modules from ``ATP TestCase Flows`` without changing YAML content."""

    __test__ = False

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.atp_root = self.repo_root / "ATP TestCase Flows"

    def _discover_flows(self, folder: str) -> list[Path]:
        # Reuse existing ATP discovery (single source of truth).
        repo = str(self.repo_root)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from execution.atp_folder_paths import discover_atp_yaml_files

        return discover_atp_yaml_files(self.repo_root, folder, exclude_subflows=True)

    def list_module_folders(self) -> list[str]:
        if not self.atp_root.is_dir():
            return []
        folders = [
            p.name
            for p in sorted(self.atp_root.iterdir(), key=lambda x: x.name.lower())
            if p.is_dir() and not p.name.startswith(".")
        ]
        return folders

    def build_plan(
        self,
        *,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> list[ModulePlan]:
        include = [x.strip() for x in (include or []) if x.strip()]
        exclude = {x.strip().lower() for x in (exclude or []) if x.strip()}

        folders = self.list_module_folders()
        if include:
            resolved: list[str] = []
            for item in include:
                alias = FEATURE_ALIASES.get(item.lower(), item)
                match = next((f for f in folders if f.lower() == alias.lower()), None)
                if match and match not in resolved:
                    resolved.append(match)
            folders = resolved

        folders = [f for f in folders if f.lower() not in exclude]

        # Stable preferred order
        ordered: list[str] = []
        for pref in PREFERRED_ORDER:
            for f in folders:
                if f.lower() == pref.lower() and f not in ordered:
                    ordered.append(f)
        for f in folders:
            if f not in ordered:
                ordered.append(f)

        plans: list[ModulePlan] = []
        for idx, folder in enumerate(ordered):
            flows = self._discover_flows(folder)
            if not flows:
                logger.warning("module %s has no runnable YAML — skipping", folder)
                continue
            plans.append(
                ModulePlan(
                    name=folder,
                    folder=folder,
                    flow_count=len(flows),
                    flow_paths=[str(p) for p in flows],
                    priority=idx,
                )
            )
            logger.info("planned module=%s flows=%s", folder, len(flows))
        return plans
