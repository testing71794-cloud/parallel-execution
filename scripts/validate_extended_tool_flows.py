#!/usr/bin/env python3
"""Validate runFlow references in extended-tool editing flows."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ATP TestCase Flows" / "editing"
FLOWS = [
    "ED_02A - Filter all-in-one comprehensive with AI.yaml",
    "ED_03A - Frames all-in-one comprehensive with AI.yaml",
    "ED_04A - Stickers all-in-one comprehensive with AI.yaml",
    "ED_Q1 - Frames module quick check.yaml",
    "ED_Q2 - Stickers module quick check.yaml",
    "ED_Q3 - Crop module quick check.yaml",
    "ED_Q4 - Rotate module quick check.yaml",
    "ED_Q5 - Flip module quick check.yaml",
    "ED_Q6 - Brightness module quick check.yaml",
    "ED_Q7 - Temperature module quick check.yaml",
    "ED_Q8 - Adjust module quick check.yaml",
    "ED_Q9 - Text module quick check.yaml",
    "ED_Q10 - Paint module quick check.yaml",
    "ED_Q11 - Blur module quick check.yaml",
    "ED_09A - Text comprehensive with AI.yaml",
    "ED_09B - Text screen navigation and UI.yaml",
    "ED_10A - Paint comprehensive with AI.yaml",
    "ED_10B - Paint screen navigation and UI.yaml",
    "ED_11A - Blur comprehensive with AI.yaml",
    "ED_11B - Blur screen navigation and UI.yaml",
    "ED_12B - Blur text paint combined with AI.yaml",
    "ED_09 - Text comprehensive.yaml",
    "ED_10 - Draw comprehensive.yaml",
    "ED_11 - Blur effects comprehensive.yaml",
    "ED_99 - Master edit module E2E.yaml",
]


def resolve(ref: str, base: Path) -> Path | None:
    ref = ref.strip().strip('"')
    if ref.startswith("file:"):
        return None
    for cand in (
        ROOT / "subflows" / ref,
        ROOT / ref,
        base.parent / ref,
        base.parent / "subflows" / ref,
    ):
        if cand.is_file():
            return cand
    return None


def main() -> int:
    missing: list[tuple[str, str]] = []
    for name in FLOWS:
        path = ROOT / name
        if not path.is_file():
            missing.append((name, "<missing flow file>"))
            continue
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"runFlow:\s*([^\n#]+)", text):
            ref = m.group(1).strip()
            if ref.startswith("file:"):
                rel = ref.split(":", 1)[1].strip()
                target = (path.parent / rel).resolve()
                if not target.is_file():
                    missing.append((name, rel))
                continue
            if ref.startswith("when:"):
                continue
            target = resolve(ref, path)
            if target is None:
                missing.append((name, ref))
    if missing:
        print("Missing runFlow references:")
        for flow, ref in missing:
            print(f"  {flow}: {ref}")
        return 1
    print(f"OK: {len(FLOWS)} flows validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
