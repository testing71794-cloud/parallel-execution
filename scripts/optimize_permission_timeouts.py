#!/usr/bin/env python3
"""Reduce permission subflow timeouts: 120000 -> 45000 (waits) or 3000 (animations)."""
from __future__ import annotations

import re
from pathlib import Path

PERM = Path(__file__).resolve().parents[1] / "ATP TestCase Flows" / "permission"

SKIP = {
    "reach_my_gallery.yaml",  # already 45000
}


def patch_file(path: Path) -> bool:
    if path.name in SKIP:
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    # extendedWaitUntil / wait timeouts
    text = re.sub(
        r"(extendedWaitUntil:[\s\S]*?timeout:\s*)120000",
        r"\g<1>45000",
        text,
    )
    # animation waits that were incorrectly set to 120s
    text = re.sub(
        r"(waitForAnimationToEnd:[\s\S]*?timeout:\s*)120000",
        r"\g<1>3000",
        text,
    )
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    changed = 0
    for path in sorted(PERM.rglob("*.yaml")):
        if patch_file(path):
            print(f"patched {path.relative_to(PERM)}")
            changed += 1
    print(f"done ({changed} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
