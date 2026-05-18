#!/usr/bin/env python3
"""Diagnostics for Maestro runFlow paths (no YAML mutation)."""
from __future__ import annotations

import re
from pathlib import Path

_RUNFLOW_INLINE = re.compile(r"^\s*-?\s*runFlow:\s*(.+?)\s*$", re.IGNORECASE)
_RUNFLOW_FILE = re.compile(r"^\s+file:\s*(.+?)\s*$", re.IGNORECASE)


def _collect_runflow_targets(yaml_path: Path) -> list[str]:
    try:
        lines = yaml_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    targets: list[str] = []
    pending_file = False
    for line in lines:
        if pending_file:
            m_file = _RUNFLOW_FILE.match(line)
            if m_file:
                targets.append(m_file.group(1).strip().strip("'\""))
                pending_file = False
                continue
            if line.strip() and not line.strip().startswith("#"):
                pending_file = False
        m_inline = _RUNFLOW_INLINE.match(line)
        if m_inline:
            val = m_inline.group(1).strip().strip("'\"")
            if not val or val.lower() == "when:":
                pending_file = True
            else:
                targets.append(val)
    return targets


def validate_runflow_paths(flow_yaml: Path, *, repo_root: Path | None = None) -> None:
    """
    Log resolved absolute paths for each runFlow reference in a flow file.
    Does not modify YAML; warnings only when target is missing.
    """
    flow_yaml = flow_yaml.resolve()
    source = str(flow_yaml)
    for target in _collect_runflow_targets(flow_yaml):
        resolved = (flow_yaml.parent / target).resolve()
        exists = resolved.is_file()
        print(
            f"[ATP] runflow_resolve source={source} target={target} "
            f"resolved={resolved} exists={str(exists).lower()}",
            flush=True,
        )
        if not exists and repo_root is not None:
            alt = (repo_root / target).resolve()
            if alt.is_file():
                print(
                    f"[ATP] runflow_resolve_hint source={source} "
                    f"repo_root_candidate={alt} exists=true",
                    flush=True,
                )
