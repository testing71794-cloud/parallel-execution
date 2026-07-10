"""Resolve Jenkins ATP stage folder names to on-disk ATP TestCase Flows directories."""
from __future__ import annotations

import os
import re
from pathlib import Path

# Jenkins stage argument aliases → Kodak Smile ATP folder names (case-insensitive match).
_CANONICAL_BY_KEY: dict[str, str] = {
    "camera": "Camera",
    "collage": "Collage",
    "connection": "Connection",
    "editing": "Editing",
    "onboarding": "Onboarding",
    "precut": "Precut",
    "printing": "Printing",
    "settings": "Settings",
    "signuplogin": "SignUp_Login",
    "signup_login": "SignUp_Login",
}


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())


def resolve_atp_subfolder(repo: Path, folder: str) -> str:
    """
    Map stage argument (e.g. Connection, SignUp_Login) to actual child folder name
  (e.g. connection, signup-login) using case-insensitive directory match.
    """
    raw = (folder or "").strip()
    if not raw:
        return ""
    target = _CANONICAL_BY_KEY.get(_norm_key(raw), raw)
    atp_root = repo / "ATP TestCase Flows"
    if atp_root.is_dir():
        for child in sorted(atp_root.iterdir()):
            if child.is_dir() and child.name.lower() == target.lower():
                return child.name
    return target


def is_subflow_helper(path: Path) -> bool:
    """Reusable Maestro subflows are run via runFlow, not as top-level Jenkins tests."""
    return any(part.lower() == "subflows" for part in path.parts)


def is_maestro_workspace_config(path: Path) -> bool:
    """Maestro per-folder config (testOutputDir, etc.) — not a runnable test flow."""
    return path.name.lower() in ("config.yaml", "config.yml")


def is_excluded_top_level_flow(path: Path) -> bool:
    """Reserved for flows that must not be discovered as top-level Jenkins tests."""
    return is_maestro_workspace_config(path)


def safe_flow_stem(name: str) -> str:
    """Filesystem-safe flow stem for Windows cmd/batch (parentheses break grouped blocks)."""
    slug = re.sub(r"[^\w\-.]+", "_", (name or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "flow"


def discover_atp_yaml_files(repo: Path, atp_subfolder: str, *, exclude_subflows: bool = True) -> list[Path]:
    atp_root = repo / "ATP TestCase Flows"
    if not atp_root.is_dir():
        return []
    sub = resolve_atp_subfolder(repo, atp_subfolder) if (atp_subfolder or "").strip() else ""
    if sub:
        folder_root = atp_root / sub
        if not folder_root.is_dir():
            return []
        roots = [folder_root]
    else:
        roots = [atp_root]
    include = (os.environ.get("ATP_FLOW_INCLUDE") or "").strip()
    exclude_raw = (os.environ.get("ATP_FLOW_EXCLUDE") or "").strip()
    exclude_parts = [p.strip().lower() for p in exclude_raw.split(",") if p.strip()]
    flows: list[Path] = []
    for root in roots:
        for p in sorted(root.rglob("*"), key=lambda x: str(x).lower()):
            if not p.is_file() or p.suffix.lower() not in (".yaml", ".yml"):
                continue
            if exclude_subflows and is_subflow_helper(p):
                continue
            if exclude_subflows and is_excluded_top_level_flow(p):
                continue
            if include and include.lower() not in p.name.lower():
                continue
            if exclude_parts and any(part in p.name.lower() for part in exclude_parts):
                continue
            flows.append(p)
    return flows
