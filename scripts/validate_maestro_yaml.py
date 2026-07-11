#!/usr/bin/env python3
"""
Validate Maestro flow YAML under ATP TestCase Flows (and optional paths).

Detects invalid optional nesting, e.g.:
  - tapOn: "Pair"
    optional: true   # INVALID — optional must be under the command key

Correct:
  - tapOn:
      text: "Pair"
      optional: true
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCALAR_CMD = re.compile(
    r"^(\s*)-\s+(tapOn|assertVisible|assertNotVisible|scrollUntilVisible|"
    r"doubleTapOn|longPressOn|copyTextFrom|pasteText|eraseText|inputText)\s*:\s*(.+)\s*$",
    re.I,
)
_OPTIONAL_SIBLING = re.compile(r"^\s+optional:\s*true\s*$", re.I)
_RUNFLOW_INLINE = re.compile(r"^\s*-?\s*runFlow:\s*(.+?)\s*$", re.I)
_RUNFLOW_FILE = re.compile(r"^\s+file:\s*(.+?)\s*$", re.I)


def _issues_for_file(yaml_path: Path, repo_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        lines = yaml_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"{yaml_path}: read error: {exc}"]

    for i, line in enumerate(lines):
        m = _SCALAR_CMD.match(line)
        if m and i + 1 < len(lines) and _OPTIONAL_SIBLING.match(lines[i + 1]):
            issues.append(
                f"{yaml_path}:{i + 1}: invalid optional on sibling line — use nested form:\n"
                f"    - {m.group(2).strip()}:\n"
                f"        text: ...\n"
                f"        optional: true"
            )

    pending_file = False
    for i, line in enumerate(lines, start=1):
        if pending_file:
            m_file = _RUNFLOW_FILE.match(line)
            if m_file:
                target = m_file.group(1).strip().strip("'\"")
                resolved = (yaml_path.parent / target).resolve()
                if not resolved.is_file():
                    alt = (repo_root / target).resolve()
                    if not alt.is_file():
                        issues.append(
                            f"{yaml_path}:{i}: runFlow file not found: {target} "
                            f"(resolved {resolved})"
                        )
                pending_file = False
            elif line.strip() and not line.strip().startswith("#"):
                pending_file = False
        m_inline = _RUNFLOW_INLINE.match(line)
        if m_inline:
            val = m_inline.group(1).strip().strip("'\"")
            if not val or val.lower() == "when:":
                pending_file = True
            else:
                resolved = (yaml_path.parent / val).resolve()
                if not resolved.is_file():
                    alt = (repo_root / val).resolve()
                    if not alt.is_file():
                        issues.append(
                            f"{yaml_path}:{i}: runFlow target not found: {val}"
                        )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Maestro YAML syntax patterns")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories (default: ATP TestCase Flows)",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    roots: list[Path] = [Path(p) for p in args.paths] if args.paths else [repo / "ATP TestCase Flows"]
    files: list[Path] = []
    for root in roots:
        root = root.resolve()
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(sorted(root.rglob("*.yaml")))
            files.extend(sorted(root.rglob("*.yml")))
    all_issues: list[str] = []
    for yf in files:
        all_issues.extend(_issues_for_file(yf, repo))
    if not all_issues:
        print(f"[validate_maestro_yaml] OK — {len(files)} file(s) checked")
        return 0
    print(f"[validate_maestro_yaml] FAILED — {len(all_issues)} issue(s):", file=sys.stderr)
    for msg in all_issues:
        print(msg, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
